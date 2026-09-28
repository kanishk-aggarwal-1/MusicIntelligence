import logging
import random
from collections import Counter
from math import log

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
from . import live_metrics_service, spotify_service
from .discovery_service import discover_songs_from_artist
from .enrichment_service import enrich_song
from .ml_recommendation_service import ALGORITHM_VERSION as ML_ALGORITHM_VERSION
from .ml_recommendation_service import knn_recommend
from .spotify_service import load_user_session, resolve_track_id

ALGORITHM_VERSION = "tfidf-knn-v1"
logger = logging.getLogger(__name__)
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
    """Upsert tags for a song.

    Uses INSERT … ON CONFLICT DO NOTHING at the SQL level instead of a
    Python-level pre-check.  The pre-check approach was fragile: it could
    miss tags already committed by a previous enrichment pass (e.g. when
    retry_partial=True re-processes partially-enriched songs), causing a
    UniqueViolation on song_tags_song_id_tag_id_key.
    """
    is_postgres = _db_engine.dialect.name == "postgresql"

    normalized_names = []
    seen_names: set[str] = set()
    for raw_name in tag_names or []:
        tag_name = (raw_name or "").strip()
        if not tag_name:
            continue
        tag_key = tag_name.lower()
        if tag_key in seen_names:
            continue
        seen_names.add(tag_key)
        normalized_names.append(tag_name)

    if not normalized_names:
        return 0

    # Bulk-fetch all existing tags in one query instead of one SELECT per name.
    existing_tags: dict[str, Tag] = {
        t.name: t for t in db.query(Tag).filter(Tag.name.in_(normalized_names)).all()
    }
    missing_names = [n for n in normalized_names if n not in existing_tags]

    if missing_names:
        if is_postgres:
            db.execute(
                postgres_insert(Tag.__table__)
                .values([{"name": n} for n in missing_names])
                .on_conflict_do_nothing(index_elements=["name"])
            )
            db.flush()
            for t in db.query(Tag).filter(Tag.name.in_(missing_names)).all():
                existing_tags[t.name] = t
        else:
            for name in missing_names:
                db.add(Tag(name=name))
            db.flush()
            for t in db.query(Tag).filter(Tag.name.in_(missing_names)).all():
                existing_tags[t.name] = t

    tag_values = [
        {"song_id": song.id, "tag_id": existing_tags[n].id}
        for n in normalized_names
        if n in existing_tags
    ]
    if not tag_values:
        return 0

    added = 0
    if is_postgres:
        result = db.execute(
            postgres_insert(SongTag.__table__)
            .values(tag_values)
            .on_conflict_do_nothing(index_elements=["song_id", "tag_id"])
        )
        added = result.rowcount or 0
        if added:
            db.flush()
    else:
        existing_tag_ids = {
            row[0]
            for row in db.query(SongTag.tag_id)
            .filter(
                SongTag.song_id == song.id,
                SongTag.tag_id.in_([v["tag_id"] for v in tag_values]),
            )
            .all()
        }
        for v in tag_values:
            if v["tag_id"] not in existing_tag_ids:
                db.add(SongTag(song_id=v["song_id"], tag_id=v["tag_id"]))
                added += 1
        if added:
            db.flush()

    return added


def _apply_enrichment(db, song, data):
    if not data:
        song.enrichment_status = "failed"
        song.enrichment_error = "No enrichment payload"
        return 0

    prior_status = song.enrichment_status
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

    # A song is "complete" once it has at least one tag — tags are what the
    # TF-IDF / discovery model actually needs.  Requiring song.genre too was
    # overly strict: many valid tracks have tags but no explicit genre string,
    # and those songs were permanently invisible to the discovery pool because
    # _score_discovery_songs filters on enrichment_status == "complete".
    if song.song_tags:
        song.enrichment_status = "complete"
        song.enrichment_error = None
    elif changed > 0:
        song.enrichment_status = "partial"
        song.enrichment_error = "; ".join(errors[:2]) if errors else "Partial metadata"
    else:
        song.enrichment_status = "failed"
        song.enrichment_error = "; ".join(errors[:2]) if errors else "No useful metadata found"

    # Count a track as "enriched" the first time real metadata moves it out of
    # "pending". On PostgreSQL this metric write succeeds immediately in its own
    # connection. On SQLite it times out silently (SQLite allows only one writer
    # at a time; the fail-open timeout in live_metrics_service handles this).
    if prior_status in (None, "pending") and song.enrichment_status in ("complete", "partial"):
        live_metrics_service.increment(live_metrics_service.TRACKS_ENRICHED)

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


def _normalize_enrichment_status(song):
    if song.is_deleted:
        return False

    has_core_metadata = bool(song.genre and song.song_tags)
    has_popularity = (song.playcount or 0) > 0 and (song.listeners or 0) > 0
    previous = song.enrichment_status

    if has_core_metadata and has_popularity:
        song.enrichment_status = "complete"
        song.enrichment_error = None
    elif song.enrichment_status == "pending" and (song.genre or song.song_tags or has_popularity):
        song.enrichment_status = "partial"
        song.enrichment_error = song.enrichment_error or "Partial metadata"

    return song.enrichment_status != previous


def sync_listening_history(db, user_id, tracks, enrich_inline=True):
    is_postgres = _db_engine.dialect.name == "postgresql"

    # Pre-load all artists and spotify-keyed songs in two bulk queries
    # instead of one SELECT per track.
    valid_items = [item for item in tracks if item.get("title") and item.get("artist")]
    unique_artist_names = {item["artist"] for item in valid_items}
    artist_by_name: dict[str, Artist] = (
        {a.name: a for a in db.query(Artist).filter(Artist.name.in_(unique_artist_names)).all()}
        if unique_artist_names
        else {}
    )

    unique_spotify_ids = {item["spotify_id"] for item in valid_items if item.get("spotify_id")}
    song_by_spotify: dict[str, Song] = (
        {
            s.spotify_id: s
            for s in db.query(Song).filter(Song.spotify_id.in_(unique_spotify_ids)).all()
        }
        if unique_spotify_ids
        else {}
    )

    new_songs = 0
    new_history_rows = 0
    existing_history_rows = 0
    pending_history_keys = set()

    for item in valid_items:
        title = item.get("title")
        artist_name = item.get("artist")
        spotify_id = item.get("spotify_id")
        artist_spotify_id = item.get("artist_spotify_id")
        image_url = item.get("image_url")
        preview_url = item.get("preview_url")

        artist = artist_by_name.get(artist_name)
        if not artist:
            artist = Artist(name=artist_name, spotify_id=artist_spotify_id)
            db.add(artist)
            db.flush()
            artist_by_name[artist_name] = artist
        elif artist_spotify_id and not artist.spotify_id:
            artist.spotify_id = artist_spotify_id

        song = song_by_spotify.get(spotify_id) if spotify_id else None

        if not song:
            song = (
                db.query(Song)
                .filter(
                    Song.title == title,
                    Song.artist_id == artist.id,
                    Song.is_deleted.is_(False),
                )
                .first()
            )

        if not song:
            song = Song(
                title=title,
                artist_id=artist.id,
                spotify_id=spotify_id,
                image_url=image_url,
                preview_url=preview_url,
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
        if image_url:
            song.image_url = image_url
        if preview_url:
            song.preview_url = preview_url

        if enrich_inline and _needs_enrichment(song):
            data = enrich_song(song)
            _apply_enrichment(db, song, data)

        played_at = _parse_played_at(item.get("played_at"))
        history_key = (user_id, song.id, played_at)

        if history_key in pending_history_keys:
            existing_history_rows += 1
            continue

        if is_postgres:
            # ON CONFLICT DO NOTHING handles duplicates — pre-check SELECT not needed.
            result = db.execute(
                postgres_insert(ListeningHistory.__table__)
                .values(
                    user_id=user_id,
                    song_id=song.id,
                    played_at=played_at,
                    ms_played=item.get("ms_played"),
                    skipped=item.get("skipped"),
                    platform=item.get("platform"),
                    country=item.get("country"),
                    offline=item.get("offline"),
                    incognito=item.get("incognito"),
                )
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
            existing = (
                db.query(ListeningHistory)
                .filter(
                    ListeningHistory.user_id == user_id,
                    ListeningHistory.song_id == song.id,
                    ListeningHistory.played_at == played_at,
                )
                .first()
                if played_at
                else db.query(ListeningHistory)
                .filter(
                    ListeningHistory.user_id == user_id,
                    ListeningHistory.song_id == song.id,
                )
                .first()
            )
            if not existing:
                db.add(
                    ListeningHistory(
                        user_id=user_id,
                        song_id=song.id,
                        played_at=played_at,
                        ms_played=item.get("ms_played"),
                        skipped=item.get("skipped"),
                        platform=item.get("platform"),
                        country=item.get("country"),
                        offline=item.get("offline"),
                        incognito=item.get("incognito"),
                    )
                )
                pending_history_keys.add(history_key)
                new_history_rows += 1
            else:
                existing_history_rows += 1

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise

    if new_history_rows:
        live_metrics_service.increment(live_metrics_service.TRACKS_SYNCED, new_history_rows)

    return {
        "new_songs": new_songs,
        "new_history_rows": new_history_rows,
        "existing_history_rows": existing_history_rows,
    }


def backfill_missing_metadata(
    db,
    user_id: str | None = None,
    max_songs=1000,
    include_partial=False,
    include_failed=False,
    commit_batch_size=50,
    progress_callback=None,
    progress_interval=5,
):
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
    processed = 0
    total_candidates = len(songs)
    report_every = max(1, int(progress_interval or 1))

    for song in songs:
        processed += 1
        if not _needs_enrichment(
            song, include_partial=include_partial, include_failed=include_failed
        ):
            if _normalize_enrichment_status(song):
                updated += 1
            if progress_callback and (
                processed == total_candidates or processed % report_every == 0
            ):
                progress_callback(
                    current=processed,
                    total=total_candidates,
                    scanned=scanned,
                    updated=updated,
                    song=song,
                )
            continue

        scanned += 1
        data = enrich_song(song)
        changed = _apply_enrichment(db, song, data)
        if changed > 0:
            updated += 1

        if scanned % max(1, commit_batch_size) == 0:
            db.commit()

        if progress_callback and (processed == total_candidates or processed % report_every == 0):
            progress_callback(
                current=processed,
                total=total_candidates,
                scanned=scanned,
                updated=updated,
                song=song,
            )

    db.commit()

    if progress_callback and total_candidates == 0:
        progress_callback(current=0, total=0, scanned=scanned, updated=updated, song=None)

    return {
        "scanned": scanned,
        "updated": updated,
        "processed": processed,
        "total_candidates": total_candidates,
        "remaining_hint": "Use retry modes to include partial or failed songs when needed.",
    }


def _tag_names(song):
    return [st.tag.name for st in song.song_tags if st.tag and st.tag.name]


def _context_match(song, context_type: str | None):
    if not context_type:
        return 0.0, "No explicit context selected."
    hints = CONTEXT_HINTS.get(context_type.lower().strip()) or set()
    haystack = {(song.genre or "").lower()}
    haystack.update(name.lower() for name in _tag_names(song))
    matched = sorted(
        hint
        for hint in hints
        if hint and any(hint in value or value in hint for value in haystack if value)
    )
    score = min(1.0, len(matched) / max(1, min(4, len(hints)))) if hints else 0.0
    if matched:
        return score, f"Context tags matched: {', '.join(matched[:3])}"
    return 0.0, "No strong context-tag match."


def _feedback_signal_map(db, user_id):
    rows = (
        db.query(
            RecommendationFeedback.song_id,
            RecommendationFeedback.action,
            func.count(RecommendationFeedback.id),
        )
        .filter(RecommendationFeedback.user_id == user_id)
        .group_by(RecommendationFeedback.song_id, RecommendationFeedback.action)
        .all()
    )

    signal_map = {}

    for song_id, action, count in rows:
        song_signals = signal_map.setdefault(song_id, Counter())
        song_signals[action] += int(count or 0)

    return signal_map


def _feedback_adjustment(
    feedback_counts,
    *,
    context_type,
    familiarity_score,
    rarity_or_discovery_score,
    quality_confidence_score,
    context_match_score,
    recently_overplayed_penalty,
    similarity,
    known_spotify_score,
):
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
            0.16
            * too_obscure_count
            * (0.7 + rarity_or_discovery_score + (1 - known_spotify_score) * 0.5),
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


def _human_reasons(
    song,
    *,
    tag_names,
    play_count,
    context_type,
    components,
    feedback_reason=None,
    is_discovery=False,
):
    reasons = []
    artist_name = song.artist.name if song.artist else None
    tags = [tag for tag in (tag_names or []) if tag]

    if is_discovery:
        # Explicitly flagged as a discovery track by knn_recommend — always
        # show the discovery label regardless of play_count on the dict.
        # Do NOT use `play_count == 0` here: library songs that were imported
        # without a listening-history row would get a misleading "new music"
        # label even though the user added them intentionally.
        if artist_name:
            reasons.append("new music — matched to your taste, not yet in your library")
        else:
            reasons.append("new music matched to your taste")
    elif play_count >= 5 and artist_name:
        reasons.append(f"because you often play {artist_name}")
    elif play_count > 0:
        reasons.append("because it already fits your listening history")

    if tags:
        reasons.append(f"matches your {tags[0]} taste")
    elif song.genre:
        reasons.append(f"matches your {song.genre} listening")

    if context_type:
        context_label = context_type.replace("-", " ")
        reasons.append(f"fits a {context_label} session")

    if components.get("co_occurrence_boost", 0) > 0:
        reasons.append("often appears near songs you replay")

    if feedback_reason:
        reasons.append("adjusted using your feedback")

    if not reasons:
        reasons.append("recommended from your overall taste profile")

    deduped = []
    seen = set()
    for reason in reasons:
        key = reason.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(reason)
    return deduped[:4]


def recommend_songs(
    db,
    user_id,
    return_details=False,
    min_known_ratio: float = 0.6,
    context_type: str | None = None,
    limit: int = 30,
    discovery_ratio: float = 0.4,
    # Legacy params — accepted but ignored; discovery now runs as a background job.
    allow_discovery: bool = True,
    include_discovery_summary: bool = False,
    discovery_seed_limit: int = 10,
    discovery_store_limit: int | None = None,
    resolve_spotify: bool = True,
    discovery_max_similar: int | None = None,
):

    logger.info("recommend_songs.start user_id=%s", user_id)

    feedback_map = _feedback_signal_map(db, user_id)
    excluded_song_ids = {
        song_id
        for song_id, counts in feedback_map.items()
        if counts.get("never_show", 0) >= 1 or counts.get("dislike", 0) >= 2
    }

    ml_results = knn_recommend(
        db,
        user_id,
        limit=limit,
        context_type=context_type,
        excluded_song_ids=excluded_song_ids,
        discovery_ratio=discovery_ratio,
    )

    if not return_details:
        return [r["song"] for r in ml_results]

    items = []
    for r in ml_results:
        song = r["song"]
        score = r["score"]
        familiarity_score = r["familiarity_score"]
        play_count = r["play_count"]

        feedback_counts = feedback_map.get(song.id, Counter())
        feedback_boost, feedback_reason = _feedback_adjustment(
            feedback_counts,
            context_type=context_type,
            familiarity_score=familiarity_score,
            rarity_or_discovery_score=0.0,
            quality_confidence_score=1.0 if song.spotify_id else 0.5,
            context_match_score=0.0,
            recently_overplayed_penalty=0.0,
            similarity=r["tfidf_similarity"],
            known_spotify_score=1.0 if song.spotify_id else 0.0,
        )
        final_score = max(0.0, min(1.0, score + feedback_boost * 0.20))

        debug_reasons = [f"TF-IDF similarity {r['tfidf_similarity']:.2f}"]
        if r["co_occurrence_boost"] > 0:
            debug_reasons.append(
                f"Often heard in the same session (+{r['co_occurrence_boost']:.2f})"
            )
        debug_reasons.append(f"Played {play_count} time{'s' if play_count != 1 else ''}")
        if feedback_reason:
            debug_reasons.append(feedback_reason.capitalize())

        components = {
            "tfidf_similarity": r["tfidf_similarity"],
            "co_occurrence_boost": r["co_occurrence_boost"],
            "familiarity_score": familiarity_score,
            "feedback_score": round(feedback_boost, 4),
            "feedback_events": int(sum(feedback_counts.values())),
            "known_spotify_score": 1.0 if song.spotify_id else 0.0,
        }
        reasons = _human_reasons(
            song,
            tag_names=r["tags"],
            play_count=play_count,
            context_type=context_type,
            components=components,
            feedback_reason=feedback_reason,
            is_discovery=r.get("is_discovery", False),
        )

        items.append(
            {
                "song": song,
                "score": final_score,
                "reasons": reasons,
                "debug_reasons": debug_reasons,
                "components": components,
                "algorithm_version": ML_ALGORITHM_VERSION,
                "tag_names": r["tags"],
            }
        )

    items.sort(key=lambda x: x["score"], reverse=True)

    return items


def build_discovery_feed(db, user_id, limit=20):
    # discovery_ratio=0.0 is required here: allow_discovery=False only suppresses
    # the Last.fm fan-out; without explicitly zeroing discovery_ratio, knn_recommend
    # would still allocate 40% of results from previously-stored discovery songs.
    details = recommend_songs(
        db, user_id, return_details=True, allow_discovery=False, discovery_ratio=0.0, limit=limit
    )

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
                "debug_reasons": item.get("debug_reasons", []),
                "components": item["components"],
                "discovery_source": song.discovery_source,
                "discovery_confidence": song.discovery_confidence,
            }
        )

    return feed


def discover_new_songs(
    db,
    user_id,
    include_summary: bool = False,
    seed_limit: int | None = None,
    max_similar_per_seed: int | None = None,
):

    logger.info("discover_new_songs.start user_id=%s include_summary=%s", user_id, include_summary)
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
    logger.info(
        "discover_new_songs.artist_rows=%s unique_artists=%s selected_seed_artists=%s seed_limit=%s",
        len(artist_rows),
        total_artists,
        len(artists),
        seed_limit,
    )

    new_songs = []
    summary = {
        "seed_artists": len(artists),
        "total_history_artists": total_artists,
        "source_artists": 0,
        "source": "lastfm",
    }

    for index, artist in enumerate(artists, start=1):
        if index == 1 or index % 10 == 0 or index == len(artists):
            logger.info(
                "discover_new_songs.artist index=%s total=%s name=%s", index, len(artists), artist
            )

        try:
            if include_summary:
                discovery_result = discover_songs_from_artist(
                    artist, include_stats=True, max_similar_artists=max_similar_per_seed
                )
                discovered = discovery_result.get("songs", [])
                summary["source_artists"] += int(discovery_result.get("source_artists") or 0)
            else:
                discovered = discover_songs_from_artist(
                    artist, max_similar_artists=max_similar_per_seed
                )
        except Exception as exc:
            logger.warning("discover_new_songs.artist_failed name=%s error=%s", artist, exc)
            discovered = []

        new_songs.extend(discovered)

    logger.info("discover_new_songs.done discovered=%s summary=%s", len(new_songs), summary)
    if include_summary:
        return new_songs, summary

    return new_songs


def store_discovered_songs(
    db, songs, user_id: str | None = None, limit: int | None = None, resolve_spotify: bool = True
):
    """Store Last.fm-discovered songs in the songs table and enrich with Last.fm metadata.

    ``resolve_spotify=False`` skips the Spotify track-ID lookup, making inline
    discovery during playlist preview ~10× faster.  Missing Spotify IDs are
    resolved lazily when the user saves the playlist (``_resolve_playlist_track_ids``
    already handles that case).
    """
    total_input = len(songs)
    if limit is not None:
        songs = songs[: max(0, int(limit))]
    logger.info(
        "store_discovered_songs.start count=%s total_input=%s limit=%s resolve_spotify=%s",
        len(songs),
        total_input,
        limit,
        resolve_spotify,
    )

    sp = None
    rate_limited = False

    if resolve_spotify:
        session = load_user_session(db, user_id=user_id)
        token = session.get("token")
        if not token:
            logger.info("store_discovered_songs.no_token — storing without Spotify IDs")
            resolve_spotify = False
        else:
            sp = spotify_service.get_spotify_client(token)

    # Pre-load all artists by name in a single query to avoid one SELECT per
    # song inside the loop.  With 60 songs from ~20 distinct artists this
    # replaces up to 60 round-trips with 1.
    all_artist_names = list({s["artist"] for s in songs if s.get("artist")})
    artist_cache: dict[str, Artist] = {
        a.name: a for a in db.query(Artist).filter(Artist.name.in_(all_artist_names)).all()
    }

    for idx, s in enumerate(songs, start=1):
        if idx == 1 or idx % 10 == 0 or idx == len(songs):
            logger.info("store_discovered_songs.progress index=%s total=%s", idx, len(songs))

        title = s["title"]
        artist_name = s["artist"]

        artist = artist_cache.get(artist_name)
        if not artist:
            artist = Artist(name=artist_name)
            db.add(artist)
            db.flush()
            artist_cache[artist_name] = artist

        # Case-insensitive title match avoids inserting duplicates that differ
        # only by capitalisation.  When resolve_spotify=False the secondary
        # dedup-by-spotify-id check is skipped (spotify_id is always None), so
        # this is the only guard against repeated preview calls accumulating
        # near-identical rows.
        exists = (
            db.query(Song)
            .filter(
                func.lower(Song.title) == title.lower().strip(),
                Song.artist_id == artist.id,
                Song.is_deleted.is_(False),
            )
            .first()
        )

        # ── Spotify ID resolution (optional, deferred when resolve_spotify=False) ──
        spotify_id = None
        if resolve_spotify and sp is not None:
            try:
                spotify_id = resolve_track_id(sp, title, artist_name)
            except Exception as exc:
                status = getattr(exc, "http_status", None)
                if status == 401:
                    logger.info(
                        "store_discovered_songs.token_expired title=%s artist=%s",
                        title,
                        artist_name,
                    )
                    refreshed_session = load_user_session(db, user_id=user_id)
                    refreshed_token = refreshed_session.get("token")
                    if not refreshed_token:
                        raise
                    sp = spotify_service.get_spotify_client(refreshed_token)
                    spotify_id = resolve_track_id(sp, title, artist_name)
                elif status == 429:
                    logger.warning(
                        "store_discovered_songs.rate_limited title=%s artist=%s", title, artist_name
                    )
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
            spotify_id=spotify_id,  # None when resolve_spotify=False; resolved at save time
            discovery_source=s.get("discovery_source") or "discovery_unknown",
            discovery_confidence=s.get("discovery_confidence") or 0.5,
            enrichment_status="pending",
            is_deleted=False,
        )
        db.add(song)
        try:
            sp = db.begin_nested()
            db.flush()
            sp.commit()
        except IntegrityError:
            sp.rollback()
            # Race condition: another concurrent request inserted the same song.
            # Re-fetch and continue as if it already existed.
            song = (
                db.query(Song)
                .filter(
                    Song.title == title,
                    Song.artist_id == artist.id,
                    Song.is_deleted.is_(False),
                )
                .first()
            )
            if not song:
                logger.warning(
                    "store_discovered_songs.recheck_miss title=%s artist_id=%s", title, artist.id
                )
                continue

        data = enrich_song(song)
        _apply_enrichment(db, song, data)

    db.commit()
    return {"store_attempted": len(songs), "store_rate_limited": rate_limited}
