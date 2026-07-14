from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import String, cast, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.artist import Artist
from ..models.listening_history import ListeningHistory
from ..models.song import Song
from ..services.spotify_service import load_request_user_session
from ..time_utils import parse_utc_datetime, to_naive_utc, utcnow

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _serialize_series(rows, label_key, value_key):
    return [{label_key: str(label), value_key: int(value)} for label, value in rows]


def _parse_date(value):
    if not value:
        return None
    parsed = parse_utc_datetime(value)
    return to_naive_utc(parsed) if parsed else None


@router.get("/stats")
def get_stats(
    request: Request,
    days: int = 30,
    start_date: str | None = None,
    end_date: str | None = None,
    compare_previous: bool = False,
    db: Session = Depends(get_db),
):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    safe_days = max(1, min(days, 365))
    latest_played_at = None
    if not end_date:
        latest_played_at = (
            db.query(func.max(ListeningHistory.played_at))
            .filter(ListeningHistory.user_id == user_id)
            .scalar()
        )
    end_dt = _parse_date(end_date) or latest_played_at or to_naive_utc(utcnow())
    start_dt = _parse_date(start_date) or (end_dt - timedelta(days=safe_days))

    artist_join = cast(Song.artist_id, String) == cast(Artist.id, String)

    base_history = db.query(ListeningHistory).filter(
        ListeningHistory.user_id == user_id,
        ListeningHistory.played_at >= start_dt,
        ListeningHistory.played_at <= end_dt,
    )

    top_artists_rows = (
        db.query(Artist.name, func.count(ListeningHistory.id))
        .join(Song, artist_join)
        .join(ListeningHistory, Song.id == ListeningHistory.song_id)
        .filter(
            ListeningHistory.user_id == user_id,
            ListeningHistory.played_at >= start_dt,
            ListeningHistory.played_at <= end_dt,
            Song.is_deleted.is_(False),
        )
        .group_by(Artist.name)
        .order_by(func.count(ListeningHistory.id).desc())
        .limit(10)
        .all()
    )

    # Distinct artists played within the selected window.
    # top_artists_rows is capped at 10 by the LIMIT, so the stat card needs a
    # separate COUNT DISTINCT that covers all artists in the period — not just
    # the top 10.  Filters match the rest of the windowed queries exactly.
    total_artists = (
        db.query(func.count(func.distinct(Artist.id)))
        .select_from(ListeningHistory)
        .join(Song, Song.id == ListeningHistory.song_id)
        .join(Artist, artist_join)
        .filter(
            ListeningHistory.user_id == user_id,
            ListeningHistory.played_at >= start_dt,
            ListeningHistory.played_at <= end_dt,
            Song.is_deleted.is_(False),
        )
        .scalar()
    ) or 0

    top_genres_rows = (
        db.query(Song.genre, func.count(ListeningHistory.id))
        .join(ListeningHistory, Song.id == ListeningHistory.song_id)
        .filter(
            Song.genre.is_not(None),
            Song.is_deleted.is_(False),
            ListeningHistory.user_id == user_id,
            ListeningHistory.played_at >= start_dt,
            ListeningHistory.played_at <= end_dt,
        )
        .group_by(Song.genre)
        .order_by(func.count(ListeningHistory.id).desc())
        .limit(10)
        .all()
    )

    daily_rows = (
        db.query(func.date(ListeningHistory.played_at), func.count(ListeningHistory.id))
        .filter(ListeningHistory.user_id == user_id, ListeningHistory.played_at >= start_dt, ListeningHistory.played_at <= end_dt)
        .group_by(func.date(ListeningHistory.played_at))
        .order_by(func.date(ListeningHistory.played_at).desc())
        .limit(60)
        .all()
    )

    weekly_rows = (
        db.query(func.date_trunc("week", ListeningHistory.played_at), func.count(ListeningHistory.id))
        .filter(ListeningHistory.user_id == user_id, ListeningHistory.played_at >= start_dt, ListeningHistory.played_at <= end_dt)
        .group_by(func.date_trunc("week", ListeningHistory.played_at))
        .order_by(func.date_trunc("week", ListeningHistory.played_at).desc())
        .limit(20)
        .all()
    )

    hourly_rows = (
        db.query(func.extract("hour", ListeningHistory.played_at), func.count(ListeningHistory.id))
        .filter(ListeningHistory.user_id == user_id, ListeningHistory.played_at >= start_dt, ListeningHistory.played_at <= end_dt)
        .group_by(func.extract("hour", ListeningHistory.played_at))
        .order_by(func.extract("hour", ListeningHistory.played_at))
        .all()
    )

    daily_genre_rows = (
        db.query(func.date(ListeningHistory.played_at), Song.genre, func.count(ListeningHistory.id))
        .join(Song, Song.id == ListeningHistory.song_id)
        .filter(
            Song.genre.is_not(None),
            Song.is_deleted.is_(False),
            ListeningHistory.user_id == user_id,
            ListeningHistory.played_at >= start_dt,
            ListeningHistory.played_at <= end_dt,
        )
        .group_by(func.date(ListeningHistory.played_at), Song.genre)
        .order_by(func.date(ListeningHistory.played_at).desc(), func.count(ListeningHistory.id).desc())
        .limit(120)
        .all()
    )

    weekly_genre_rows = (
        db.query(func.date_trunc("week", ListeningHistory.played_at), Song.genre, func.count(ListeningHistory.id))
        .join(Song, Song.id == ListeningHistory.song_id)
        .filter(
            Song.genre.is_not(None),
            Song.is_deleted.is_(False),
            ListeningHistory.user_id == user_id,
            ListeningHistory.played_at >= start_dt,
            ListeningHistory.played_at <= end_dt,
        )
        .group_by(func.date_trunc("week", ListeningHistory.played_at), Song.genre)
        .order_by(func.date_trunc("week", ListeningHistory.played_at).desc(), func.count(ListeningHistory.id).desc())
        .limit(120)
        .all()
    )

    total_plays = base_history.count()
    total_ms = base_history.with_entities(func.sum(ListeningHistory.ms_played)).scalar() or 0
    known_skip_rows = base_history.filter(ListeningHistory.skipped.is_not(None)).count()
    skipped_rows = base_history.filter(ListeningHistory.skipped.is_(True)).count()

    compare_payload = None
    if compare_previous:
        span = end_dt - start_dt
        prev_end = start_dt
        prev_start = start_dt - span

        prev_total = (
            db.query(func.count(ListeningHistory.id))
            .filter(ListeningHistory.user_id == user_id, ListeningHistory.played_at >= prev_start, ListeningHistory.played_at < prev_end)
            .scalar()
        ) or 0

        delta = total_plays - prev_total
        compare_payload = {
            "current_total_plays": int(total_plays),
            "previous_total_plays": int(prev_total),
            "delta": int(delta),
            "delta_percent": round((delta / prev_total) * 100, 2) if prev_total else None,
            "previous_window": {
                "start": prev_start.isoformat(),
                "end": prev_end.isoformat(),
            },
        }

    top_artists = _serialize_series(top_artists_rows, "artist", "plays")
    top_genres = _serialize_series(top_genres_rows, "genre", "plays")
    daily_listening = _serialize_series(daily_rows, "day", "plays")
    weekly_listening = _serialize_series(weekly_rows, "week", "plays")
    hourly_listening = _serialize_series(hourly_rows, "hour", "plays")

    daily_genre = [
        {"day": str(day), "genre": genre, "plays": int(plays)}
        for day, genre, plays in daily_genre_rows
    ]

    weekly_genre = [
        {"week": str(week), "genre": genre, "plays": int(plays)}
        for week, genre, plays in weekly_genre_rows
    ]

    return {
        "window": {"start": start_dt.isoformat(), "end": end_dt.isoformat(), "days": safe_days},
        "total_plays": int(total_plays),
        "minutes_listened": round(int(total_ms) / 60000),
        "skip_rate_percent": round((skipped_rows / known_skip_rows) * 100, 1) if known_skip_rows else None,
        "total_artists": int(total_artists),
        "comparison": compare_payload,
        "top_artists": top_artists,
        "top_genres": top_genres,
        "daily_listening": daily_listening,
        "weekly_listening": weekly_listening,
        "hourly_listening": hourly_listening,
        "daily_genre": daily_genre,
        "weekly_genre": weekly_genre,
    }
