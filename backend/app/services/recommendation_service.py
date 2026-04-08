from collections import Counter
from datetime import datetime
from math import log, sqrt
import random


from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..models.artist import Artist
from ..models.listening_history import ListeningHistory
from ..models.recommendation_feedback import RecommendationFeedback
from ..models.song import Song
from ..models.song_tag import SongTag
from ..models.tag import Tag

from .discovery_service import discover_songs_from_artist
from .enrichment_service import enrich_song
from .spotify_service import load_user_session, resolve_track_id
from . import spotify_service


def _parse_played_at(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


def _ensure_song_tags(db, song, tag_names):
    added = 0
    normalized_names = []
    seen_names = set()

    for raw_name in tag_names or []:
        tag_name = (raw_name or "").strip()
        if not tag_name:
            continue
        tag_key = tag_name.lower()
        if tag_key in seen_names:
            continue
        seen_names.add(tag_key)
        normalized_names.append(tag_name)

    existing_tag_ids = {
        row[0]
        for row in db.query(SongTag.tag_id).filter(SongTag.song_id == song.id).all()
        if row[0] is not None
    }
    existing_tag_ids.update(
        obj.tag_id
        for obj in db.new
        if isinstance(obj, SongTag) and obj.song_id == song.id and obj.tag_id is not None
    )

    for tag_name in normalized_names:
        tag = db.query(Tag).filter(Tag.name == tag_name).first()

        if not tag:
            tag = Tag(name=tag_name)
            db.add(tag)
            db.flush()

        if tag.id in existing_tag_ids:
            continue

        db.add(SongTag(song_id=song.id, tag_id=tag.id))
        existing_tag_ids.add(tag.id)
        added += 1

    if added:
        db.flush()

    return added


def _apply_enrichment(db, song, data):
    if not data:
        song.enrichment_status = "failed"
        song.enrichment_error = "No enrichment payload"
        return 0

    changed = 0

    if not song.genre and data.get("genre"):
        song.genre = data.get("genre")
        changed += 1


    listeners = data.get("listeners") or 0
    playcount = data.get("playcount") or 0

    old_listeners = song.listeners or 0
    old_playcount = song.playcount or 0

    song.listeners = max(old_listeners, listeners)
    song.playcount = max(old_playcount, playcount)

    if song.listeners != old_listeners:
        changed += 1
    if song.playcount != old_playcount:
        changed += 1

    base = song.playcount if song.playcount > 0 else song.listeners
    new_score = log(base + 1)
    if (song.popularity_score or 0) != new_score:
        song.popularity_score = new_score
        changed += 1

    tags = data.get("tags", [])
    changed += _ensure_song_tags(db, song, tags)
    errors = [str(err) for err in data.get("_errors", []) if err]

    if song.genre and song.song_tags:
        song.enrichment_status = "complete"
        song.enrichment_error = None
    elif changed > 0:
        song.enrichment_status = "partial"
        song.enrichment_error = "; ".join(errors[:2]) if errors else "Partial metadata"
    else:
        song.enrichment_status = "failed"
        song.enrichment_error = "; ".join(errors[:2]) if errors else "No useful metadata found"

    return changed


def _needs_enrichment(song, include_partial=True, include_failed=False):
    if song.is_deleted:
        return False
    if song.enrichment_status == "complete":
        return False
    if song.enrichment_status == "failed" and not include_failed:
        return False
    if not include_partial and song.enrichment_status == "partial":
        return False

    return (
        not song.genre
        or not song.song_tags
        or (song.playcount or 0) == 0
        or (song.listeners or 0) == 0
    )


def sync_listening_history(db, user_id, tracks):

    new_songs = 0
    new_history_rows = 0
    existing_history_rows = 0

    for item in tracks:
        title = item.get("title")
        artist_name = item.get("artist")
        spotify_id = item.get("spotify_id")

        if not title or not artist_name:
            continue

        artist = db.query(Artist).filter(Artist.name == artist_name).first()

        if not artist:
            artist = Artist(name=artist_name)
            db.add(artist)
            db.flush()

        song = None

        if spotify_id:
            song = db.query(Song).filter(Song.spotify_id == spotify_id).first()

        if not song:
            song = db.query(Song).filter(
                Song.title == title,
                Song.artist_id == artist.id,
                Song.is_deleted.is_(False),
            ).first()

        if not song:
            song = Song(
                title=title,
                artist_id=artist.id,
                spotify_id=spotify_id,
                discovery_source="history_sync",
                discovery_confidence=1.0,
                enrichment_status="pending",
                is_deleted=False,
            )
            db.add(song)
            db.flush()
            new_songs += 1

        if song.artist_id != artist.id:
            song.artist_id = artist.id

        song.is_deleted = False

        if spotify_id and not song.spotify_id:
            song.spotify_id = spotify_id

        if _needs_enrichment(song):
            data = enrich_song(song)
            _apply_enrichment(db, song, data)

        played_at = _parse_played_at(item.get("played_at"))

        if played_at:
            existing = db.query(ListeningHistory).filter(
                ListeningHistory.user_id == user_id,
                ListeningHistory.song_id == song.id,
                ListeningHistory.played_at == played_at
            ).first()
        else:
            existing = db.query(ListeningHistory).filter(
                ListeningHistory.user_id == user_id,
                ListeningHistory.song_id == song.id
            ).first()

        if not existing:
            history = ListeningHistory(
                user_id=user_id,
                song_id=song.id,
                played_at=played_at
            )
            db.add(history)
            new_history_rows += 1
        else:
            existing_history_rows += 1

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise

    return {
        "new_songs": new_songs,
        "new_history_rows": new_history_rows,
        "existing_history_rows": existing_history_rows,
    }


def backfill_missing_metadata(db, user_id: str | None = None, max_songs=1000, include_partial=False, include_failed=False, commit_batch_size=50):
    query = (
        db.query(Song)
        .join(Artist, Song.artist_id == Artist.id)
        .filter(
            Song.is_deleted.is_(False),
            Song.enrichment_status != "complete",
        )
    )

    if user_id:
        user_song_ids = (
            db.query(ListeningHistory.song_id)
            .filter(ListeningHistory.user_id == user_id)
            .distinct()
            .subquery()
        )
        query = query.join(user_song_ids, user_song_ids.c.song_id == Song.id)

    if not include_failed:
        query = query.filter(Song.enrichment_status != "failed")

    if not include_partial:
        query = query.filter(Song.enrichment_status != "partial")

    songs = query.limit(max_songs).all()

    updated = 0
    scanned = 0

    for song in songs:
        if not _needs_enrichment(song, include_partial=include_partial, include_failed=include_failed):
            continue

        scanned += 1
        data = enrich_song(song)
        changed = _apply_enrichment(db, song, data)
        if changed > 0:
            updated += 1

        if scanned % max(1, commit_batch_size) == 0:
            db.commit()

    db.commit()

    return {
        "scanned": scanned,
        "updated": updated,
        "remaining_hint": "Use retry modes to include partial or failed songs when needed."
    }


def build_user_profile(db, user_id):

    history = db.query(ListeningHistory).join(Song, Song.id == ListeningHistory.song_id).filter(
        ListeningHistory.user_id == user_id,
        Song.is_deleted.is_(False),
    ).all()

    tag_counter = Counter()

    for h in history:

        song = h.song

        if not song.song_tags:
            continue

        for st in song.song_tags:

            tag_counter[st.tag.name] += 1

    return tag_counter


def build_song_vector(song):

    vector = {}

    for st in song.song_tags:

        vector[st.tag.name] = 1

    return vector


def build_user_vector(profile):

    return dict(profile)


def cosine_similarity(vec1, vec2):

    intersection = set(vec1.keys()) & set(vec2.keys())

    numerator = sum(vec1[x] * vec2[x] for x in intersection)

    sum1 = sum(v ** 2 for v in vec1.values())

    sum2 = sum(v ** 2 for v in vec2.values())

    denominator = sqrt(sum1) * sqrt(sum2)

    if denominator == 0:

        return 0

    score = numerator / denominator
    if abs(score - 1.0) < 1e-12:
        return 1.0
    return score


def _feedback_weight_map(db, user_id):
    rows = (
        db.query(RecommendationFeedback.song_id, RecommendationFeedback.action, func.count(RecommendationFeedback.id))
        .filter(RecommendationFeedback.user_id == user_id)
        .group_by(RecommendationFeedback.song_id, RecommendationFeedback.action)
        .all()
    )

    weight_map = {}

    for song_id, action, count in rows:
        weight_map.setdefault(song_id, 0.0)
        if action == "like":
            weight_map[song_id] += 0.25 * count
        elif action == "skip":
            weight_map[song_id] -= 0.10 * count
        elif action == "dislike":
            weight_map[song_id] -= 0.35 * count

    return weight_map


def recommend_songs(db, user_id, return_details=False, min_known_ratio: float = 0.6, include_discovery_summary: bool = False, allow_discovery: bool = True, discovery_seed_limit: int | None = None, discovery_store_limit: int | None = None):

    print(f"recommend_songs.start user_id={user_id} include_discovery_summary={include_discovery_summary}")
    discovery_summary = {
        "seed_artists": 0,
        "total_history_artists": 0,
        "source_artists": 0,
        "source": "disabled" if not allow_discovery else "lastfm",
        "store_attempted": 0,
        "store_rate_limited": False,
    }
    if allow_discovery and include_discovery_summary:
        discovered, discovery_summary = discover_new_songs(db, user_id, include_summary=True, seed_limit=discovery_seed_limit)
    elif allow_discovery:
        discovered = discover_new_songs(db, user_id, seed_limit=discovery_seed_limit)
    else:
        discovered = []

    if allow_discovery:
        store_summary = store_discovered_songs(db, discovered, user_id=user_id, limit=discovery_store_limit)
        if include_discovery_summary and discovery_summary is not None:
            discovery_summary.update(store_summary)

    profile = build_user_profile(db, user_id)
    user_vector = build_user_vector(profile)
    feedback_map = _feedback_weight_map(db, user_id)

    songs = db.query(Song).filter(Song.is_deleted.is_(False)).all()

    scored = []

    for song in songs:

        if not song.song_tags:
            continue

        song_vector = build_song_vector(song)

        similarity = cosine_similarity(user_vector, song_vector)
        popularity = song.popularity_score or 0
        feedback_boost = feedback_map.get(song.id, 0.0)

        similarity_component = similarity * 0.65
        popularity_component = popularity * 0.25
        feedback_component = feedback_boost * 0.10

        score = similarity_component + popularity_component + feedback_component

        reasons = [
            f"Tag similarity: {similarity:.2f}",
            f"Popularity signal: {popularity:.2f}",
            f"Data source: {song.discovery_source or 'unknown'}",
        ]

        if feedback_boost > 0:
            reasons.append("Boosted by your positive feedback")
        elif feedback_boost < 0:
            reasons.append("Lowered by your skip/dislike feedback")

        scored.append((score, song, reasons, {
            "similarity_component": round(similarity_component, 4),
            "popularity_component": round(popularity_component, 4),
            "feedback_component": round(feedback_component, 4),
        }))

    scored.sort(key=lambda x: x[0], reverse=True)

    top = scored[:30]

    if return_details:
        items = [
            {
                "song": s,
                "score": score,
                "reasons": reasons,
                "components": components,
            }
            for score, s, reasons, components in top
        ]
        if include_discovery_summary:
            return {"items": items, "discovery_summary": discovery_summary}
        return items

    songs_only = [s for _, s, _, _ in top]
    if include_discovery_summary:
        return {"items": songs_only, "discovery_summary": discovery_summary}
    return songs_only


def build_discovery_feed(db, user_id, limit=20):
    details = recommend_songs(db, user_id, return_details=True)

    feed = []
    for item in details[:limit]:
        song = item["song"]
        feed.append(
            {
                "song_id": song.id,
                "title": song.title,
                "artist": song.artist.name if song.artist else None,
                "spotify_id": song.spotify_id,
                "score": round(item["score"], 4),
                "reasons": item["reasons"],
                "components": item["components"],
                "discovery_source": song.discovery_source,
                "discovery_confidence": song.discovery_confidence,
            }
        )

    return feed


def discover_new_songs(db, user_id, include_summary: bool = False, seed_limit: int | None = None):

    print(f"discover_new_songs.start user_id={user_id} include_summary={include_summary}")
    artist_rows = (
        db.query(Artist.name, func.count(ListeningHistory.id).label("plays"))
        .join(Song, Song.artist_id == Artist.id)
        .join(ListeningHistory, ListeningHistory.song_id == Song.id)
        .filter(
            ListeningHistory.user_id == user_id,
            Song.is_deleted.is_(False),
            Artist.name.is_not(None),
        )
        .group_by(Artist.name)
        .all()
    )

    weighted_artists = [(name, int(plays or 0)) for name, plays in artist_rows if name]
    total_artists = len(weighted_artists)
    if seed_limit is None:
        selected = weighted_artists
    else:
        limit = max(1, min(int(seed_limit), total_artists)) if total_artists else 0
        bucket_seed = datetime.utcnow().strftime("%Y%m%d%H")
        rng = random.Random(bucket_seed)
        pool = weighted_artists[:]
        selected = []
        while pool and len(selected) < limit:
            total_weight = sum(max(1, weight) for _, weight in pool)
            pick = rng.uniform(0, total_weight)
            upto = 0.0
            chosen_index = 0
            for idx, (_, weight) in enumerate(pool):
                upto += max(1, weight)
                if upto >= pick:
                    chosen_index = idx
                    break
            selected.append(pool.pop(chosen_index))

    artists = [name for name, _ in selected]
    print(f"discover_new_songs.artist_rows={len(artist_rows)} unique_artists={total_artists} selected_seed_artists={len(artists)} seed_limit={seed_limit}")

    new_songs = []
    summary = {
        "seed_artists": len(artists),
        "total_history_artists": total_artists,
        "source_artists": 0,
        "source": "lastfm",
    }

    for index, artist in enumerate(artists, start=1):
        if index == 1 or index % 10 == 0 or index == len(artists):
            print(f"discover_new_songs.artist {index}/{len(artists)} name={artist}")

        if include_summary:
            discovery_result = discover_songs_from_artist(artist, include_stats=True)
            discovered = discovery_result.get("songs", [])
            summary["source_artists"] += int(discovery_result.get("source_artists") or 0)
        else:
            discovered = discover_songs_from_artist(artist)

        new_songs.extend(discovered)

    print(f"discover_new_songs.done discovered={len(new_songs)} summary={summary}")
    if include_summary:
        return new_songs, summary

    return new_songs


def store_discovered_songs(db, songs, user_id: str | None = None, limit: int | None = None):

    total_input = len(songs)
    if limit is not None:
        songs = songs[: max(0, int(limit))]
    print(f"store_discovered_songs.start count={len(songs)} total_input={total_input} limit={limit}")
    session = load_user_session(db, user_id=user_id)
    token = session.get("token")
    rate_limited = False

    if not token:
        return {"store_attempted": len(songs), "store_rate_limited": False}

    sp = spotify_service.get_spotify_client(token)

    for idx, s in enumerate(songs, start=1):
        if idx == 1 or idx % 10 == 0 or idx == len(songs):
            print(f"store_discovered_songs.progress {idx}/{len(songs)}")

        title = s["title"]

        artist_name = s["artist"]

        artist = db.query(Artist).filter(
            Artist.name == artist_name
        ).first()

        if not artist:

            artist = Artist(name=artist_name)

            db.add(artist)

            db.flush()

        exists = db.query(Song).filter(
            Song.title == title,
            Song.artist_id == artist.id,
            Song.is_deleted.is_(False),
        ).first()

        try:
            spotify_id = resolve_track_id(sp, title, artist_name)
        except Exception as exc:
            status = getattr(exc, "http_status", None)
            if status == 401:
                print(f"store_discovered_songs.token_expired refreshing title={title} artist={artist_name}")
                refreshed_session = load_user_session(db, user_id=user_id)
                refreshed_token = refreshed_session.get("token")
                if not refreshed_token:
                    raise
                sp = spotify_service.get_spotify_client(refreshed_token)
                spotify_id = resolve_track_id(sp, title, artist_name)
            elif status == 429:
                print(f"store_discovered_songs.rate_limited title={title} artist={artist_name}")
                rate_limited = True
                spotify_id = None
                break
            else:
                raise
        if not exists and spotify_id:
            exists = db.query(Song).filter(Song.spotify_id == spotify_id).first()

        if exists:
            exists.is_deleted = False
            if not exists.artist_id:
                exists.artist_id = artist.id
            if not exists.spotify_id and spotify_id:
                exists.spotify_id = spotify_id
            if not exists.discovery_source:
                exists.discovery_source = s.get("discovery_source") or "discovery_unknown"
            if not exists.discovery_confidence:
                exists.discovery_confidence = s.get("discovery_confidence") or 0.5

            data = enrich_song(exists)
            _apply_enrichment(db, exists, data)
            continue

        song = Song(
            title=title,
            artist_id=artist.id,
            spotify_id=spotify_id,
            discovery_source=s.get("discovery_source") or "discovery_unknown",
            discovery_confidence=s.get("discovery_confidence") or 0.5,
            enrichment_status="pending",
            is_deleted=False,
        )

        db.add(song)
        db.flush()

        data = enrich_song(song)

        _apply_enrichment(db, song, data)

    db.commit()
    return {"store_attempted": len(songs), "store_rate_limited": rate_limited}













