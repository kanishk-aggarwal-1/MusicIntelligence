import json
import re
import uuid
from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..database import get_db, engine as _db_engine
from ..models.artist import Artist
from ..models.dedup_merge_log import DedupMergeLog
from ..models.listening_goal import ListeningGoal
from ..models.listening_history import ListeningHistory
from ..models.recommendation_feedback import RecommendationFeedback
from ..models.song import Song
from ..models.song_tag import SongTag
from ..models.tag import Tag
from ..services.api_cache_service import clear_provider_cache, get_cached_response, store_cached_response
from ..services.discovery_service import discover_songs_from_artist
from ..services.rate_limit_service import enforce_rate_limit
from ..services.recommendation_service import build_discovery_feed
from ..services.spotify_service import load_request_user_session
from ..time_utils import utcnow_naive

router = APIRouter(prefix="/insights", tags=["Insights"])


def _month_trunc(col):
    if _db_engine.dialect.name == "postgresql":
        return func.date_trunc("month", col)
    return func.strftime("%Y-%m-01", col)


class FeedbackPayload(BaseModel):
    song_id: int
    action: str


class GoalPayload(BaseModel):
    goal_type: str
    target_value: int
    period: str = "weekly"


def _canonical_title(title: str):
    t = (title or "").lower()
    t = re.sub(r"\([^\)]*\)", "", t)
    t = re.sub(r"\b(remaster(ed)?|live|version|mono|stereo|edit|deluxe)\b", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _duplicate_groups(db: Session, user_id: str):
    rows = (
        db.query(Song.id, Song.title, Song.spotify_id, Song.genre, Artist.name, Song.artist_id)
        .join(ListeningHistory, ListeningHistory.song_id == Song.id)
        .join(Artist, Artist.id == Song.artist_id)
        .filter(ListeningHistory.user_id == user_id, Song.is_deleted.is_(False))
        .distinct()
        .all()
    )

    groups = {}

    for song_id, title, spotify_id, genre, artist_name, artist_id in rows:
        key = f"{(artist_name or '').lower().strip()}::{_canonical_title(title or '')}"
        groups.setdefault(key, []).append(
            {
                "song_id": song_id,
                "title": title,
                "artist": artist_name,
                "artist_id": artist_id,
                "spotify_id": spotify_id,
                "genre": genre,
            }
        )

    duplicates = [
        {"group_key": k, "songs": sorted(v, key=lambda x: x["song_id"]), "count": len(v)}
        for k, v in groups.items()
        if len(v) > 1
    ]

    duplicates.sort(key=lambda x: x["count"], reverse=True)
    return duplicates


def _require_user_id(db: Session, request: Request):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")
    return user_id


@router.get("/taste-timeline")
def taste_timeline(request: Request, months: int = 6, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)
    safe_months = max(1, min(months, 24))

    artist_rows = (
        db.query(
            _month_trunc(ListeningHistory.played_at).label("month"),
            Artist.name,
            func.count(ListeningHistory.id).label("plays"),
        )
        .join(Song, Song.id == ListeningHistory.song_id)
        .join(Artist, Artist.id == Song.artist_id)
        .filter(ListeningHistory.user_id == user_id, Song.is_deleted.is_(False))
        .group_by(_month_trunc(ListeningHistory.played_at), Artist.name)
        .order_by(_month_trunc(ListeningHistory.played_at).desc(), func.count(ListeningHistory.id).desc())
        .limit(safe_months * 5)
        .all()
    )

    genre_rows = (
        db.query(
            _month_trunc(ListeningHistory.played_at).label("month"),
            Song.genre,
            func.count(ListeningHistory.id).label("plays"),
        )
        .join(Song, Song.id == ListeningHistory.song_id)
        .filter(ListeningHistory.user_id == user_id, Song.genre.is_not(None), Song.is_deleted.is_(False))
        .group_by(_month_trunc(ListeningHistory.played_at), Song.genre)
        .order_by(_month_trunc(ListeningHistory.played_at).desc(), func.count(ListeningHistory.id).desc())
        .limit(safe_months * 5)
        .all()
    )

    monthly_top_artists = [
        {"month": str(m), "artist": a, "plays": int(p)}
        for m, a, p in artist_rows
    ]

    monthly_top_genres = [
        {"month": str(m), "genre": g, "plays": int(p)}
        for m, g, p in genre_rows
    ]

    return {
        "monthly_top_artists": monthly_top_artists,
        "monthly_top_genres": monthly_top_genres,
    }


@router.get("/discovery-feed")
def discovery_feed(request: Request, limit: int = 20, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)
    safe_limit = max(1, min(limit, 100))
    feed = build_discovery_feed(db, user_id, limit=safe_limit)
    return {"items": feed}


# How many of the user's top artists to fan out to Last.fm, and how many
# similar artists to query per source. Both bound the worst-case number of
# (rate-limited) Last.fm calls on a cold cache.
NEW_FOR_YOU_SOURCE_ARTISTS = 5
NEW_FOR_YOU_SIMILAR_PER_SOURCE = 6
NEW_FOR_YOU_TARGET = 10

# Successful discoveries are stable for hours; an empty result usually means a
# transient Last.fm failure, so it gets a short TTL to avoid locking the user
# out of discoveries for hours after a brief outage.
NEW_FOR_YOU_TTL_OK = timedelta(hours=6)
NEW_FOR_YOU_TTL_EMPTY = timedelta(minutes=10)


def _spotify_url_for_track(item: dict):
    """Resolve a usable Spotify link for a discovered track.

    Last.fm discoveries carry no Spotify IDs, so fall back to a Spotify search
    URL built from title + artist — always actionable, never a dead end.
    """
    spotify_url = item.get("spotify_url") or item.get("external_url")
    if spotify_url:
        return spotify_url
    spotify_id = item.get("spotify_id")
    if spotify_id:
        return f"https://open.spotify.com/track/{spotify_id}"
    title = (item.get("title") or "").strip()
    artist = (item.get("artist") or "").strip()
    if title and artist:
        query = quote(f"{title} {artist}")
        return f"https://open.spotify.com/search/{query}"
    return None


@router.get("/new-for-you")
def new_for_you(request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)
    cache_key = f"new_for_you:{user_id}"
    cached = get_cached_response("insights", cache_key)
    if cached and cached.get("payload") is not None:
        return cached["payload"]

    # Cache miss means we're about to fan out to Last.fm — rate limit only this
    # path so cached reads stay free but cold lookups can't hammer the API.
    enforce_rate_limit(request, namespace="new_for_you", user_id=user_id, limit=5, window_seconds=60)

    def _store(payload, *, results):
        # Long TTL only when we actually produced discoveries; short TTL on empty
        # results so a transient Last.fm failure isn't cached for hours.
        ttl = NEW_FOR_YOU_TTL_OK if results else NEW_FOR_YOU_TTL_EMPTY
        store_cached_response("insights", cache_key, payload=payload, ttl=ttl)
        return payload

    artist_rows = (
        db.query(Artist.name, func.count(ListeningHistory.id).label("plays"))
        .join(Song, Song.id == ListeningHistory.song_id)
        .join(Artist, Artist.id == Song.artist_id)
        .filter(
            ListeningHistory.user_id == user_id,
            Song.is_deleted.is_(False),
            Artist.name.is_not(None),
        )
        .group_by(Artist.name)
        .order_by(func.count(ListeningHistory.id).desc())
        .limit(NEW_FOR_YOU_SOURCE_ARTISTS)
        .all()
    )

    if len(artist_rows) < 5:
        # Too few artists is a stable structural state, not a failure — cache long.
        return _store({"items": [], "distinct_artist_count": len(artist_rows)}, results=True)

    # Build the "already listened" set from DISTINCT songs in the user's
    # library, not one row per play — otherwise a heavy listener with tens of
    # thousands of plays loads tens of thousands of duplicate rows into memory.
    user_song_ids = (
        db.query(ListeningHistory.song_id)
        .filter(ListeningHistory.user_id == user_id)
        .distinct()
        .subquery()
    )
    listened_rows = (
        db.query(Song.title, Artist.name, Song.spotify_id)
        .join(Artist, Artist.id == Song.artist_id)
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(Song.is_deleted.is_(False))
        .all()
    )
    listened_spotify_ids = {spotify_id for _, _, spotify_id in listened_rows if spotify_id}
    listened_keys = {
        ((title or "").strip().lower(), (artist or "").strip().lower())
        for title, artist, _ in listened_rows
    }

    items = []
    seen = set()
    for artist_name, _plays in artist_rows:
        try:
            discovered = discover_songs_from_artist(
                artist_name, max_similar_artists=NEW_FOR_YOU_SIMILAR_PER_SOURCE
            )
        except Exception:
            continue

        for item in discovered:
            title = (item.get("title") or "").strip()
            artist = (item.get("artist") or "").strip()
            if not title or not artist:
                continue

            spotify_id = item.get("spotify_id")
            normalized = (title.lower(), artist.lower())
            if spotify_id and spotify_id in listened_spotify_ids:
                continue
            if normalized in listened_keys or normalized in seen:
                continue

            seen.add(normalized)
            items.append(
                {
                    "title": title,
                    "artist": artist,
                    "spotify_url": _spotify_url_for_track(item),
                    "reason": f"Similar to {artist_name}",
                }
            )
            if len(items) >= NEW_FOR_YOU_TARGET:
                return _store({"items": items, "distinct_artist_count": len(artist_rows)}, results=True)

    # Empty results (transient Last.fm failure, or everything already listened)
    # get a short TTL so we retry soon rather than caching emptiness for hours.
    payload = {"items": items, "distinct_artist_count": len(artist_rows)}
    return _store(payload, results=bool(items))


def _pct_rows(rows, total):
    if not total:
        return []
    return [
        {"name": name, "pct": int(round((float(value or 0) / total) * 100))}
        for name, value in rows
        if name
    ]


@router.get("/taste-profile")
def taste_profile(request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)
    user_song_ids = (
        db.query(ListeningHistory.song_id)
        .filter(ListeningHistory.user_id == user_id)
        .distinct()
        .subquery()
    )

    all_tag_rows = (
        db.query(Tag.name, func.sum(func.coalesce(SongTag.weight, 1.0)).label("weight"))
        .join(SongTag, SongTag.tag_id == Tag.id)
        .join(user_song_ids, user_song_ids.c.song_id == SongTag.song_id)
        .group_by(Tag.name)
        .order_by(func.sum(func.coalesce(SongTag.weight, 1.0)).desc())
        .all()
    )
    total_tag_weight = sum(float(weight or 0) for _name, weight in all_tag_rows)

    total_tagged_songs = (
        db.query(func.count(func.distinct(SongTag.song_id)))
        .join(user_song_ids, user_song_ids.c.song_id == SongTag.song_id)
        .scalar()
    ) or 0

    all_genre_rows = (
        db.query(Song.genre, func.count(func.distinct(Song.id)).label("songs"))
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(Song.genre.is_not(None), Song.is_deleted.is_(False))
        .group_by(Song.genre)
        .order_by(func.count(func.distinct(Song.id)).desc())
        .all()
    )
    total_genre_count = sum(int(count or 0) for _name, count in all_genre_rows)

    if total_tagged_songs >= 100:
        profile_strength = "strong"
    elif total_tagged_songs >= 30:
        profile_strength = "moderate"
    else:
        profile_strength = "building"

    return {
        "top_tags": _pct_rows(all_tag_rows[:6], total_tag_weight),
        "top_genres": _pct_rows(all_genre_rows[:4], total_genre_count),
        "total_tagged_songs": int(total_tagged_songs),
        "profile_strength": profile_strength,
    }


@router.post("/feedback")
def add_feedback(payload: FeedbackPayload, request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)

    action = payload.action.lower().strip()
    allowed_actions = {
        "like",
        "dislike",
        "skip",
        "too_familiar",
        "too_obscure",
        "wrong_vibe",
        "more_like_this",
        "never_show",
    }
    if action not in allowed_actions:
        raise HTTPException(
            status_code=400,
            detail="action must be one of like/dislike/skip/too_familiar/too_obscure/wrong_vibe/more_like_this/never_show",
        )

    db.add(RecommendationFeedback(user_id=user_id, song_id=payload.song_id, action=action))
    db.commit()

    return {"message": "Feedback saved", "song_id": payload.song_id, "action": action}


@router.get("/feedback-summary")
def feedback_summary(request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)

    rows = (
        db.query(RecommendationFeedback.action, func.count(RecommendationFeedback.id))
        .filter(RecommendationFeedback.user_id == user_id)
        .group_by(RecommendationFeedback.action)
        .all()
    )

    return {"summary": [{"action": a, "count": int(c)} for a, c in rows]}


@router.post("/goals")
def create_goal(payload: GoalPayload, request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)

    goal = ListeningGoal(
        user_id=user_id,
        goal_type=payload.goal_type,
        target_value=payload.target_value,
        period=payload.period,
        active=True,
    )
    db.add(goal)
    db.commit()

    return {"message": "Goal created", "goal_id": goal.id}


@router.get("/goals-status")
def goals_status(request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)

    goals = (
        db.query(ListeningGoal)
        .filter(ListeningGoal.user_id == user_id, ListeningGoal.active.is_(True))
        .all()
    )

    now = utcnow_naive()
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

    total_events = (
        db.query(func.count(ListeningHistory.id))
        .filter(ListeningHistory.user_id == user_id, ListeningHistory.played_at >= week_start)
        .scalar()
    ) or 0

    distinct_songs = (
        db.query(func.count(func.distinct(ListeningHistory.song_id)))
        .filter(ListeningHistory.user_id == user_id, ListeningHistory.played_at >= week_start)
        .scalar()
    ) or 0

    active_days = (
        db.query(func.count(func.distinct(func.date(ListeningHistory.played_at))))
        .filter(ListeningHistory.user_id == user_id, ListeningHistory.played_at >= week_start)
        .scalar()
    ) or 0

    repeat_rate = ((total_events - distinct_songs) / total_events) if total_events > 0 else 0

    statuses = []

    for goal in goals:
        progress = 0

        if goal.goal_type == "new_songs_per_week":
            progress = distinct_songs
        elif goal.goal_type == "listening_days_per_week":
            progress = active_days
        elif goal.goal_type == "repeat_rate_max":
            progress = round(repeat_rate * 100)

        statuses.append(
            {
                "goal_id": goal.id,
                "goal_type": goal.goal_type,
                "target": goal.target_value,
                "progress": progress,
                "period": goal.period,
                "status": "on_track" if progress >= goal.target_value and goal.goal_type != "repeat_rate_max" else "check",
            }
        )

    return {"goals": statuses}


@router.delete("/goals/{goal_id}")
def delete_goal(goal_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)
    goal = (
        db.query(ListeningGoal)
        .filter(ListeningGoal.id == goal_id, ListeningGoal.user_id == user_id, ListeningGoal.active.is_(True))
        .first()
    )
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    goal.active = False
    db.add(goal)
    db.commit()
    return {"message": "Goal removed", "goal_id": goal_id}


@router.get("/data-quality")
def data_quality(request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)

    user_song_ids = (
        db.query(ListeningHistory.song_id)
        .filter(ListeningHistory.user_id == user_id)
        .distinct()
        .subquery()
    )

    base_songs = db.query(Song.id).join(user_song_ids, user_song_ids.c.song_id == Song.id).filter(Song.is_deleted.is_(False))
    total_songs = base_songs.count()

    with_genre = (
        db.query(func.count(Song.id))
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(Song.genre.is_not(None), Song.is_deleted.is_(False))
        .scalar()
    ) or 0
    with_spotify = (
        db.query(func.count(Song.id))
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(Song.spotify_id.is_not(None), Song.is_deleted.is_(False))
        .scalar()
    ) or 0

    with_tags = (
        db.query(func.count(func.distinct(SongTag.song_id)))
        .join(Song, Song.id == SongTag.song_id)
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(Song.is_deleted.is_(False))
        .scalar()
    ) or 0

    with_history = (
        db.query(func.count(func.distinct(ListeningHistory.song_id)))
        .join(Song, Song.id == ListeningHistory.song_id)
        .filter(ListeningHistory.user_id == user_id, Song.is_deleted.is_(False))
        .scalar()
    ) or 0

    status_rows = (
        db.query(Song.enrichment_status, func.count(Song.id))
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(Song.is_deleted.is_(False))
        .group_by(Song.enrichment_status)
        .all()
    )

    missing_tags = (
        db.query(func.count(Song.id))
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .outerjoin(SongTag, SongTag.song_id == Song.id)
        .filter(Song.is_deleted.is_(False), SongTag.id.is_(None))
        .scalar()
    ) or 0

    missing_popularity = (
        db.query(func.count(Song.id))
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(
            Song.is_deleted.is_(False),
            (Song.listeners.is_(None) | (Song.listeners == 0)),
            (Song.playcount.is_(None) | (Song.playcount == 0)),
        )
        .scalar()
    ) or 0

    error_rows = (
        db.query(Song.enrichment_error, func.count(Song.id))
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(Song.is_deleted.is_(False), Song.enrichment_error.is_not(None))
        .group_by(Song.enrichment_error)
        .order_by(func.count(Song.id).desc())
        .limit(10)
        .all()
    )

    artist_quality_rows = (
        db.query(
            Artist.name,
            func.count(Song.id).label("songs"),
            func.sum(case((Song.genre.is_(None), 1), else_=0)).label("missing_genre"),
            func.sum(case((Song.enrichment_status == "failed", 1), else_=0)).label("failed_count"),
        )
        .join(Song, Song.artist_id == Artist.id)
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(Song.is_deleted.is_(False))
        .group_by(Artist.name)
        .order_by(func.sum(case((Song.enrichment_status == "failed", 1), else_=0)).desc(), func.count(Song.id).desc())
        .limit(10)
        .all()
    )

    def pct(value):
        return round((value / total_songs) * 100, 2) if total_songs else 0

    return {
        "total_songs": total_songs,
        "coverage": [
            {"metric": "Songs with Genre", "count": with_genre, "percent": pct(with_genre)},
            {"metric": "Songs with Spotify ID", "count": with_spotify, "percent": pct(with_spotify)},
            {"metric": "Songs with Tags", "count": with_tags, "percent": pct(with_tags)},
            {"metric": "Songs with Listen History", "count": with_history, "percent": pct(with_history)},
        ],
        "enrichment_status": [
            {"status": s or "unknown", "count": int(c)}
            for s, c in status_rows
        ],
        "missing": {
            "tags": int(missing_tags),
            "listeners_or_playcount": int(missing_popularity),
        },
        "top_enrichment_errors": [
            {"error": err, "count": int(count)}
            for err, count in error_rows
        ],
        "artists_with_poor_metadata": [
            {
                "artist": artist_name,
                "songs": int(songs),
                "missing_genre": int(missing_genre or 0),
                "failed_count": int(failed_count or 0),
            }
            for artist_name, songs, missing_genre, failed_count in artist_quality_rows
        ],
    }


@router.post("/cache/clear")
def clear_cache(request: Request, provider: str = "lastfm", db: Session = Depends(get_db)):
    _require_user_id(db, request)
    cleared = clear_provider_cache(provider)
    return {"message": "Cache cleared", "provider": provider, "cleared": cleared}


@router.get("/dedup-preview")
def dedup_preview(request: Request, limit_groups: int = 50, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)
    duplicates = _duplicate_groups(db, user_id)
    return {"duplicate_groups": duplicates[: max(1, min(limit_groups, 200))]}


@router.post("/dedup-apply")
def dedup_apply(request: Request, limit_groups: int = 20, dry_run: bool = False, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)
    duplicates = _duplicate_groups(db, user_id)[: max(1, min(limit_groups, 200))]

    if dry_run:
        return {
            "message": "Dry run complete",
            "groups": len(duplicates),
            "potential_merges": sum(max(0, g["count"] - 1) for g in duplicates),
            "duplicate_groups": duplicates,
        }

    batch_id = str(uuid.uuid4())
    merged = 0

    for group in duplicates:
        songs = group["songs"]
        keep_id = songs[0]["song_id"]

        for duplicate in songs[1:]:
            dup_id = duplicate["song_id"]

            # Identify dup rows that would collide with keep_id's existing (user_id, played_at)
            keep_pairs = {
                (r.user_id, r.played_at)
                for r in db.query(ListeningHistory.user_id, ListeningHistory.played_at)
                .filter(ListeningHistory.song_id == keep_id)
                .all()
            }
            dup_rows = db.query(ListeningHistory).filter(ListeningHistory.song_id == dup_id).all()
            conflict_ids = {r.id for r in dup_rows if (r.user_id, r.played_at) in keep_pairs}
            history_row_ids = [r.id for r in dup_rows if r.id not in conflict_ids]

            if conflict_ids:
                db.query(ListeningHistory).filter(ListeningHistory.id.in_(conflict_ids)).delete(synchronize_session=False)
                db.flush()

            tag_rows = db.query(SongTag.tag_id, SongTag.weight, SongTag.popularity, SongTag.spotify_id).filter(SongTag.song_id == dup_id).all()

            snapshot = {
                "history_row_ids": history_row_ids,
                "tag_rows": [
                    {
                        "tag_id": int(tid),
                        "weight": weight,
                        "popularity": popularity,
                        "spotify_id": sid,
                    }
                    for tid, weight, popularity, sid in tag_rows
                ],
            }

            db.query(ListeningHistory).filter(ListeningHistory.song_id == dup_id).update(
                {ListeningHistory.song_id: keep_id},
                synchronize_session=False,
            )

            keep_tag_ids = {
                row[0]
                for row in db.query(SongTag.tag_id).filter(SongTag.song_id == keep_id).all()
            }

            for tag_id, weight, popularity, spotify_id in tag_rows:
                if tag_id not in keep_tag_ids:
                    db.add(
                        SongTag(
                            song_id=keep_id,
                            tag_id=tag_id,
                            weight=weight,
                            popularity=popularity,
                            spotify_id=spotify_id,
                        )
                    )

            db.query(SongTag).filter(SongTag.song_id == dup_id).delete(synchronize_session=False)

            db.add(
                DedupMergeLog(
                    user_id=user_id,
                    batch_id=batch_id,
                    kept_song_id=keep_id,
                    removed_song_id=dup_id,
                    original_title=duplicate.get("title"),
                    original_artist=duplicate.get("artist"),
                    snapshot_json=json.dumps(snapshot),
                )
            )

            db.query(Song).filter(Song.id == dup_id).update(
                {Song.is_deleted: True},
                synchronize_session=False,
            )
            merged += 1

    db.commit()

    return {"message": "Deduplication complete", "merged_songs": merged, "batch_id": batch_id}


@router.post("/dedup-undo/{batch_id}")
def dedup_undo(batch_id: str, request: Request, db: Session = Depends(get_db)):
    user_id = _require_user_id(db, request)
    rows = db.query(DedupMergeLog).filter(DedupMergeLog.user_id == user_id, DedupMergeLog.batch_id == batch_id).all()
    if not rows:
        raise HTTPException(status_code=404, detail="Batch not found")

    undone = 0

    for row in rows:
        db.query(Song).filter(Song.id == row.removed_song_id).update(
            {Song.is_deleted: False},
            synchronize_session=False,
        )

        snapshot = {}
        try:
            snapshot = json.loads(row.snapshot_json or "{}")
        except Exception:
            snapshot = {}

        history_ids = snapshot.get("history_row_ids", [])
        if history_ids:
            db.query(ListeningHistory).filter(ListeningHistory.id.in_(history_ids)).update(
                {ListeningHistory.song_id: row.removed_song_id},
                synchronize_session=False,
            )

        for tag_item in snapshot.get("tag_rows", []):
            exists = db.query(SongTag).filter(
                SongTag.song_id == row.removed_song_id,
                SongTag.tag_id == tag_item.get("tag_id"),
            ).first()
            if exists:
                continue
            db.add(
                SongTag(
                    song_id=row.removed_song_id,
                    tag_id=tag_item.get("tag_id"),
                    weight=tag_item.get("weight"),
                    popularity=tag_item.get("popularity"),
                    spotify_id=tag_item.get("spotify_id"),
                )
            )

        undone += 1

    db.commit()

    return {"message": "Undo complete", "batch_id": batch_id, "restored": undone}


@router.get("/tags")
def user_tags(request: Request, limit: int = 100, db: Session = Depends(get_db)):
    """Return tags present in the user's listening history, ranked by play count."""
    user_id = _require_user_id(db, request)
    safe_limit = max(1, min(limit, 500))

    user_song_ids = (
        db.query(ListeningHistory.song_id)
        .filter(ListeningHistory.user_id == user_id)
        .distinct()
        .subquery()
    )

    from ..models.tag import Tag as _Tag
    rows = (
        db.query(
            _Tag.name,
            func.count(SongTag.song_id.distinct()).label("song_count"),
        )
        .join(SongTag, SongTag.tag_id == _Tag.id)
        .join(user_song_ids, user_song_ids.c.song_id == SongTag.song_id)
        .group_by(_Tag.name)
        .order_by(func.count(SongTag.song_id.distinct()).desc())
        .limit(safe_limit)
        .all()
    )

    return {"tags": [{"name": name, "song_count": int(count)} for name, count in rows]}


@router.get("/tags/{tag_name}/songs")
def songs_by_tag(tag_name: str, request: Request, limit: int = 50, db: Session = Depends(get_db)):
    """Return the user's songs that carry a given Last.fm tag."""
    user_id = _require_user_id(db, request)
    safe_limit = max(1, min(limit, 200))

    from ..models.tag import Tag as _Tag
    from sqlalchemy.orm import joinedload as _joinedload

    tag = db.query(_Tag).filter(_Tag.name == tag_name).first()
    if not tag:
        return {"songs": []}

    user_song_ids = (
        db.query(ListeningHistory.song_id)
        .filter(ListeningHistory.user_id == user_id)
        .distinct()
        .subquery()
    )

    songs = (
        db.query(Song)
        .options(_joinedload(Song.artist))
        .join(SongTag, SongTag.song_id == Song.id)
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(SongTag.tag_id == tag.id, Song.is_deleted.is_(False))
        .order_by(Song.popularity_score.desc().nullslast())
        .limit(safe_limit)
        .all()
    )

    return {
        "tag": tag_name,
        "songs": [
            {
                "id": s.id,
                "title": s.title,
                "artist": s.artist.name if s.artist else None,
                "spotify_id": s.spotify_id,
                "image_url": s.image_url,
                "preview_url": s.preview_url,
                "genre": s.genre,
                "popularity_score": s.popularity_score,
                "enrichment_status": s.enrichment_status,
            }
            for s in songs
        ],
    }

