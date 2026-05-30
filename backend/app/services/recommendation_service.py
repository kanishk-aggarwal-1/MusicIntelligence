from collections import Counter
from datetime import timedelta
from math import log, sqrt
import random


from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.exc import IntegrityError

from ..database import engine as _db_engine

from ..models.artist import Artist
from ..models.listening_history import ListeningHistory
from ..models.recommendation_feedback import RecommendationFeedback
from ..models.song import Song
from ..models.song_tag import SongTag
from ..models.tag import Tag
from ..time_utils import parse_utc_datetime, to_naive_utc, utcnow

from .discovery_service import discover_songs_from_artist
from .enrichment_service import enrich_song
from .spotify_service import load_user_session, resolve_track_id
from . import spotify_service


ALGORITHM_VERSION = "heuristic-v2"
CONTEXT_HINTS = {
    "focus": {"ambient", "instrumental", "classical", "lofi", "study", "piano", "minimal"},
    "workout": {"hip hop", "edm", "dance", "rock", "energetic", "gym", "trap", "drum and bass"},
    "late-night": {"chill", "soul", "jazz", "ambient", "electronic", "night", "downtempo", "rnb"},
    "chill": {"chill", "acoustic", "indie", "relax", "ambient", "dream pop", "lofi"},
}


def _parse_played_at(value):
    if not value:
        return None
    parsed = parse_utc_datetime(value)
    if not parsed:
        return None
    return to_naive_utc(parsed)


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
    pending_history_keys = set()

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
        history_key = (user_id, song.id, played_at)

        if history_key in pending_history_keys:
            existing_history_rows += 1
            continue

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
            if _db_engine.dialect.name == "postgresql":
                result = db.execute(
                    postgres_insert(ListeningHistory.__table__)
                    .values(user_id=user_id, song_id=song.id, played_at=played_at)
                    .on_conflict_do_nothing(
                        index_elements=["user_id", "song_id", "played_at"],
                    )
                )
                if result.rowcount:
                    new_history_rows += 1
                    pending_history_keys.add(history_key)
                else:
                    existing_history_rows += 1
            else:
                history = ListeningHistory(
                    user_id=user_id,
                    song_id=song.id,
                    played_at=played_at
                )
                db.add(history)
                pending_history_keys.add(history_key)
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


def _tag_names(song):
    return [st.tag.name for st in song.song_tags if st.tag and st.tag.name]


def _norm_log(value, max_value):
    if max_value <= 0 or value <= 0:
        return 0.0
    return min(1.0, log(value + 1) / log(max_value + 1))


def _listening_stats(db, user_id):
    song_rows = (
        db.query(
            ListeningHistory.song_id,
            func.count(ListeningHistory.id).label("plays"),
            func.max(ListeningHistory.played_at).label("last_played"),
        )
        .filter(ListeningHistory.user_id == user_id)
        .group_by(ListeningHistory.song_id)
        .all()
    )
    artist_rows = (
        db.query(
            Song.artist_id,
            func.count(ListeningHistory.id).label("plays"),
        )
        .join(ListeningHistory, ListeningHistory.song_id == Song.id)
        .filter(ListeningHistory.user_id == user_id, Song.is_deleted.is_(False))
        .group_by(Song.artist_id)
        .all()
    )

    now = to_naive_utc(utcnow())
    recent_cutoff = now - timedelta(days=14)
    recent_song_rows = (
        db.query(ListeningHistory.song_id, func.count(ListeningHistory.id))
        .filter(ListeningHistory.user_id == user_id, ListeningHistory.played_at >= recent_cutoff)
        .group_by(ListeningHistory.song_id)
        .all()
    )

    song_play_counts = {song_id: int(plays or 0) for song_id, plays, _ in song_rows}
    last_played_map = {song_id: last_played for song_id, _, last_played in song_rows}
    artist_play_counts = {artist_id: int(plays or 0) for artist_id, plays in artist_rows if artist_id is not None}
    recent_song_counts = {song_id: int(plays or 0) for song_id, plays in recent_song_rows}

    return {
        "song_play_counts": song_play_counts,
        "artist_play_counts": artist_play_counts,
        "recent_song_counts": recent_song_counts,
        "last_played_map": last_played_map,
        "max_song_plays": max(song_play_counts.values(), default=0),
        "max_artist_plays": max(artist_play_counts.values(), default=0),
        "now": now,
    }


def _context_match(song, context_type: str | None):
    if not context_type:
        return 0.0, "No explicit context selected."
    hints = CONTEXT_HINTS.get(context_type.lower().strip()) or set()
    haystack = {(song.genre or "").lower()}
    haystack.update(name.lower() for name in _tag_names(song))
    matched = sorted(hint for hint in hints if hint and any(hint in value or value in hint for value in haystack if value))
    score = min(1.0, len(matched) / max(1, min(4, len(hints)))) if hints else 0.0
    if matched:
        return score, f"Context tags matched: {', '.join(matched[:3])}"
    return 0.0, "No strong context-tag match."


def _feedback_signal_map(db, user_id):
    rows = (
        db.query(RecommendationFeedback.song_id, RecommendationFeedback.action, func.count(RecommendationFeedback.id))
        .filter(RecommendationFeedback.user_id == user_id)
        .group_by(RecommendationFeedback.song_id, RecommendationFeedback.action)
        .all()
    )

    signal_map = {}

    for song_id, action, count in rows:
        song_signals = signal_map.setdefault(song_id, Counter())
        song_signals[action] += int(count or 0)

    return signal_map


def _feedback_adjustment(feedback_counts, *, context_type, familiarity_score, rarity_or_discovery_score, quality_confidence_score, context_match_score, recently_overplayed_penalty, similarity, known_spotify_score):
    if not feedback_counts:
        return 0.0, None

    adjustment = 0.0
    notes = []

    like_count = int(feedback_counts.get("like", 0))
    if like_count:
        boost = min(0.35, 0.12 * like_count + quality_confidence_score * 0.05)
        adjustment += boost
        notes.append("reinforced by likes")

    more_like_this_count = int(feedback_counts.get("more_like_this", 0))
    if more_like_this_count:
        boost = min(
            0.45,
            0.14 * more_like_this_count
            + similarity * 0.07
            + context_match_score * 0.05
            + known_spotify_score * 0.03,
        )
        adjustment += boost
        notes.append("aligned with your 'more like this' feedback")

    skip_count = int(feedback_counts.get("skip", 0))
    if skip_count:
        penalty = min(0.18, 0.08 * skip_count)
        adjustment -= penalty
        notes.append("softened by skips")

    dislike_count = int(feedback_counts.get("dislike", 0))
    if dislike_count:
        penalty = min(0.55, 0.22 * dislike_count)
        adjustment -= penalty
        notes.append("penalized by dislikes")

    too_familiar_count = int(feedback_counts.get("too_familiar", 0))
    if too_familiar_count:
        penalty = min(
            0.45,
            0.16 * too_familiar_count * (0.7 + familiarity_score + recently_overplayed_penalty),
        )
        adjustment -= penalty
        notes.append("dialed back because similar picks felt too familiar")

    too_obscure_count = int(feedback_counts.get("too_obscure", 0))
    if too_obscure_count:
        penalty = min(
            0.45,
            0.16 * too_obscure_count * (0.7 + rarity_or_discovery_score + (1 - known_spotify_score) * 0.5),
        )
        adjustment -= penalty
        notes.append("dialed back because similar picks felt too obscure")

    wrong_vibe_count = int(feedback_counts.get("wrong_vibe", 0))
    if wrong_vibe_count:
        penalty = min(
            0.5,
            0.18 * wrong_vibe_count * (1.2 if context_type else 0.9),
        )
        adjustment -= penalty
        notes.append("penalized because the vibe feedback was negative")

    adjustment = max(-1.0, min(1.0, adjustment))
    if not notes:
        return adjustment, None
    return adjustment, "; ".join(notes)


def recommend_songs(
    db,
    user_id,
    return_details=False,
    min_known_ratio: float = 0.6,
    include_discovery_summary: bool = False,
    allow_discovery: bool = True,
    discovery_seed_limit: int | None = None,
    discovery_store_limit: int | None = None,
    context_type: str | None = None,
    limit: int = 30,
):

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
    feedback_map = _feedback_signal_map(db, user_id)
    listening_stats = _listening_stats(db, user_id)

    user_song_ids = (
        db.query(ListeningHistory.song_id)
        .filter(ListeningHistory.user_id == user_id)
        .distinct()
        .subquery()
    )
    songs = (
        db.query(Song)
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(Song.is_deleted.is_(False))
        .all()
    )

    # Hard-exclude songs the user never wants to see again, or has disliked repeatedly.
    excluded_song_ids = {
        song_id
        for song_id, counts in feedback_map.items()
        if counts.get("never_show", 0) >= 1 or counts.get("dislike", 0) >= 2
    }

    scored = []

    for song in songs:
        if song.id in excluded_song_ids:
            continue
        if not song.song_tags:
            continue

        song_vector = build_song_vector(song)
        similarity = cosine_similarity(user_vector, song_vector)
        popularity = song.popularity_score or 0
        feedback_counts = feedback_map.get(song.id, Counter())
        song_play_count = listening_stats["song_play_counts"].get(song.id, 0)
        artist_play_count = listening_stats["artist_play_counts"].get(song.artist_id, 0)
        recent_song_count = listening_stats["recent_song_counts"].get(song.id, 0)
        last_played = listening_stats["last_played_map"].get(song.id)

        context_match_score, context_reason = _context_match(song, context_type)
        familiarity_score = _norm_log(song_play_count, listening_stats["max_song_plays"])
        diversity_score = 1 - _norm_log(artist_play_count, listening_stats["max_artist_plays"])

        if last_played:
            days_since_last = max(0, (listening_stats["now"] - last_played).days)
            freshness_score = min(1.0, days_since_last / 30)
        else:
            days_since_last = None
            freshness_score = 1.0

        rarity_or_discovery_score = max(0.0, min(1.0, (1 - familiarity_score) * 0.7 + (1 if song.discovery_source and song.discovery_source != "history_sync" else 0) * 0.3))
        quality_confidence_score = min(
            1.0,
            (
                (1.0 if song.spotify_id else 0.0)
                + (0.6 if song.enrichment_status == "complete" else 0.3 if song.enrichment_status == "partial" else 0.0)
                + min(1.0, popularity / 5.0)
            ) / 2.6,
        )
        repetition_penalty = min(1.0, recent_song_count / 5)
        recently_overplayed_penalty = min(1.0, familiarity_score * 0.7 + _norm_log(recent_song_count, 10) * 0.3)
        feedback_boost, feedback_reason = _feedback_adjustment(
            feedback_counts,
            context_type=context_type,
            familiarity_score=familiarity_score,
            rarity_or_discovery_score=rarity_or_discovery_score,
            quality_confidence_score=quality_confidence_score,
            context_match_score=context_match_score,
            recently_overplayed_penalty=recently_overplayed_penalty,
            similarity=similarity,
            known_spotify_score=1.0 if song.spotify_id else 0.0,
        )

        components = {
            "context_match_score": round(context_match_score, 4),
            "familiarity_score": round(familiarity_score, 4),
            "diversity_score": round(diversity_score, 4),
            "freshness_score": round(freshness_score, 4),
            "rarity_or_discovery_score": round(rarity_or_discovery_score, 4),
            "quality_confidence_score": round(quality_confidence_score, 4),
            "feedback_score": round(max(-1.0, min(1.0, feedback_boost)), 4),
            "feedback_events": int(sum(feedback_counts.values())),
            "repetition_penalty": round(repetition_penalty, 4),
            "recently_overplayed_penalty": round(recently_overplayed_penalty, 4),
            "tag_similarity_score": round(similarity, 4),
            "known_spotify_score": 1.0 if song.spotify_id else 0.0,
        }

        score = (
            similarity * 0.26
            + context_match_score * 0.18
            + familiarity_score * 0.12
            + diversity_score * 0.10
            + freshness_score * 0.09
            + rarity_or_discovery_score * 0.07
            + quality_confidence_score * 0.08
            + (1.0 if song.spotify_id else 0.0) * 0.05
            + feedback_boost * 0.20
            - repetition_penalty * 0.10
            - recently_overplayed_penalty * 0.05
        )

        reasons = [
            f"Tag similarity {similarity:.2f}",
            context_reason,
            f"Familiarity {familiarity_score:.2f} / diversity {diversity_score:.2f}",
            f"Freshness {freshness_score:.2f}" + (f" ({days_since_last} days since last play)" if days_since_last is not None else ""),
            f"Quality confidence {quality_confidence_score:.2f}",
        ]

        if song.spotify_id:
            reasons.append("Already Spotify-resolvable")
        if feedback_reason:
            reasons.append(feedback_reason.capitalize())
        elif feedback_boost > 0:
            reasons.append("Boosted by your positive feedback")
        elif feedback_boost < 0:
            reasons.append("Lowered by your previous feedback")

        scored.append((score, song, reasons, components))

    scored.sort(key=lambda x: x[0], reverse=True)

    top = scored[: max(1, min(limit, 100))]

    if return_details:
        items = [
            {
                "song": s,
                "score": score,
                "reasons": reasons,
                "components": components,
                "algorithm_version": ALGORITHM_VERSION,
                "tag_names": _tag_names(s),
            }
            for score, s, reasons, components in top
        ]
        if include_discovery_summary:
            return {"items": items, "discovery_summary": discovery_summary, "algorithm_version": ALGORITHM_VERSION}
        return items

    songs_only = [s for _, s, _, _ in top]
    if include_discovery_summary:
        return {"items": songs_only, "discovery_summary": discovery_summary, "algorithm_version": ALGORITHM_VERSION}
    return songs_only


def build_discovery_feed(db, user_id, limit=20):
    details = recommend_songs(db, user_id, return_details=True, allow_discovery=False, limit=limit)

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
        bucket_seed = utcnow().strftime("%Y%m%d%H")
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













