from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import String, cast, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_user_id
from ..models.artist import Artist
from ..models.listening_history import ListeningHistory
from ..models.song import Song
from ..time_utils import parse_utc_datetime, to_naive_utc, utcnow

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Some deployments stored artist_id as text and others as int; cast both sides so
# the Song<->Artist join works regardless of column type.
_ARTIST_JOIN = cast(Song.artist_id, String) == cast(Artist.id, String)


def _serialize_series(rows, label_key, value_key):
    return [{label_key: str(label), value_key: int(value)} for label, value in rows]


def _parse_date(value):
    if not value:
        return None
    parsed = parse_utc_datetime(value)
    return to_naive_utc(parsed) if parsed else None


def _window(user_id: str, start_dt, end_dt):
    """Shared listening-history window filter (inclusive of both bounds)."""
    return (
        ListeningHistory.user_id == user_id,
        ListeningHistory.played_at >= start_dt,
        ListeningHistory.played_at <= end_dt,
    )


def _top_artists(db, user_id, start_dt, end_dt):
    return (
        db.query(Artist.name, func.count(ListeningHistory.id))
        .join(Song, _ARTIST_JOIN)
        .join(ListeningHistory, Song.id == ListeningHistory.song_id)
        .filter(*_window(user_id, start_dt, end_dt), Song.is_deleted.is_(False))
        .group_by(Artist.name)
        .order_by(func.count(ListeningHistory.id).desc())
        .limit(10)
        .all()
    )


def _total_artists(db, user_id, start_dt, end_dt):
    # Distinct artists across the whole window — the top_artists LIMIT 10 can't
    # provide this, so the stat card needs its own COUNT DISTINCT.
    return (
        db.query(func.count(func.distinct(Artist.id)))
        .select_from(ListeningHistory)
        .join(Song, Song.id == ListeningHistory.song_id)
        .join(Artist, _ARTIST_JOIN)
        .filter(*_window(user_id, start_dt, end_dt), Song.is_deleted.is_(False))
        .scalar()
    ) or 0


def _top_genres(db, user_id, start_dt, end_dt):
    return (
        db.query(Song.genre, func.count(ListeningHistory.id))
        .join(ListeningHistory, Song.id == ListeningHistory.song_id)
        .filter(
            Song.genre.is_not(None),
            Song.is_deleted.is_(False),
            *_window(user_id, start_dt, end_dt),
        )
        .group_by(Song.genre)
        .order_by(func.count(ListeningHistory.id).desc())
        .limit(10)
        .all()
    )


def _listening_series(db, user_id, start_dt, end_dt):
    """Return (daily, weekly, hourly) play-count rows for the window."""
    w = _window(user_id, start_dt, end_dt)
    daily = (
        db.query(func.date(ListeningHistory.played_at), func.count(ListeningHistory.id))
        .filter(*w)
        .group_by(func.date(ListeningHistory.played_at))
        .order_by(func.date(ListeningHistory.played_at).desc())
        .limit(60)
        .all()
    )
    weekly = (
        db.query(
            func.date_trunc("week", ListeningHistory.played_at), func.count(ListeningHistory.id)
        )
        .filter(*w)
        .group_by(func.date_trunc("week", ListeningHistory.played_at))
        .order_by(func.date_trunc("week", ListeningHistory.played_at).desc())
        .limit(20)
        .all()
    )
    hourly = (
        db.query(func.extract("hour", ListeningHistory.played_at), func.count(ListeningHistory.id))
        .filter(*w)
        .group_by(func.extract("hour", ListeningHistory.played_at))
        .order_by(func.extract("hour", ListeningHistory.played_at))
        .all()
    )
    return daily, weekly, hourly


def _genre_series(db, user_id, start_dt, end_dt):
    """Return (daily_genre, weekly_genre) rows for the window."""
    w = _window(user_id, start_dt, end_dt)
    daily_genre = (
        db.query(func.date(ListeningHistory.played_at), Song.genre, func.count(ListeningHistory.id))
        .join(Song, Song.id == ListeningHistory.song_id)
        .filter(Song.genre.is_not(None), Song.is_deleted.is_(False), *w)
        .group_by(func.date(ListeningHistory.played_at), Song.genre)
        .order_by(
            func.date(ListeningHistory.played_at).desc(), func.count(ListeningHistory.id).desc()
        )
        .limit(120)
        .all()
    )
    weekly_genre = (
        db.query(
            func.date_trunc("week", ListeningHistory.played_at),
            Song.genre,
            func.count(ListeningHistory.id),
        )
        .join(Song, Song.id == ListeningHistory.song_id)
        .filter(Song.genre.is_not(None), Song.is_deleted.is_(False), *w)
        .group_by(func.date_trunc("week", ListeningHistory.played_at), Song.genre)
        .order_by(
            func.date_trunc("week", ListeningHistory.played_at).desc(),
            func.count(ListeningHistory.id).desc(),
        )
        .limit(120)
        .all()
    )
    return daily_genre, weekly_genre


def _engagement_totals(db, user_id, start_dt, end_dt):
    """Return (total_plays, total_ms, known_skip_rows, skipped_rows).

    ms_played / skipped are recent columns; on older DB instances that lack them
    the aggregate raises, so fall back to a plain play count.
    """
    try:
        row = (
            db.query(
                func.count(ListeningHistory.id),
                func.coalesce(func.sum(ListeningHistory.ms_played), 0),
                func.count(ListeningHistory.id).filter(ListeningHistory.skipped.is_not(None)),
                func.count(ListeningHistory.id).filter(ListeningHistory.skipped.is_(True)),
            )
            .filter(*_window(user_id, start_dt, end_dt))
            .one()
        )
        total_plays, total_ms, known_skip_rows, skipped_rows = row
        return (
            int(total_plays or 0),
            int(total_ms or 0),
            int(known_skip_rows or 0),
            int(skipped_rows or 0),
        )
    except Exception:
        db.rollback()
        total_plays = (
            db.query(func.count(ListeningHistory.id))
            .filter(*_window(user_id, start_dt, end_dt))
            .scalar()
            or 0
        )
        return int(total_plays), 0, 0, 0


def _comparison(db, user_id, start_dt, end_dt, total_plays):
    """Compare the window's play count against the immediately preceding window."""
    span = end_dt - start_dt
    prev_end = start_dt
    prev_start = start_dt - span
    prev_total = (
        db.query(func.count(ListeningHistory.id))
        .filter(
            ListeningHistory.user_id == user_id,
            ListeningHistory.played_at >= prev_start,
            ListeningHistory.played_at < prev_end,
        )
        .scalar()
    ) or 0
    delta = total_plays - prev_total
    return {
        "current_total_plays": int(total_plays),
        "previous_total_plays": int(prev_total),
        "delta": int(delta),
        "delta_percent": round((delta / prev_total) * 100, 2) if prev_total else None,
        "previous_window": {"start": prev_start.isoformat(), "end": prev_end.isoformat()},
    }


@router.get("/stats")
def get_stats(
    request: Request,
    days: int = 30,
    start_date: str | None = None,
    end_date: str | None = None,
    compare_previous: bool = False,
    db: Session = Depends(get_db),
):
    user_id = require_user_id(db, request)

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

    top_artists_rows = _top_artists(db, user_id, start_dt, end_dt)
    total_artists = _total_artists(db, user_id, start_dt, end_dt)
    top_genres_rows = _top_genres(db, user_id, start_dt, end_dt)
    daily_rows, weekly_rows, hourly_rows = _listening_series(db, user_id, start_dt, end_dt)
    daily_genre_rows, weekly_genre_rows = _genre_series(db, user_id, start_dt, end_dt)
    total_plays, total_ms, known_skip_rows, skipped_rows = _engagement_totals(
        db, user_id, start_dt, end_dt
    )
    compare_payload = (
        _comparison(db, user_id, start_dt, end_dt, total_plays) if compare_previous else None
    )

    return {
        "window": {"start": start_dt.isoformat(), "end": end_dt.isoformat(), "days": safe_days},
        "total_plays": int(total_plays),
        "total_artists": int(total_artists),
        "minutes_listened": round(int(total_ms) / 60000),
        "skip_rate_percent": round((skipped_rows / known_skip_rows) * 100, 1)
        if known_skip_rows
        else None,
        "comparison": compare_payload,
        "top_artists": _serialize_series(top_artists_rows, "artist", "plays"),
        "top_genres": _serialize_series(top_genres_rows, "genre", "plays"),
        "daily_listening": _serialize_series(daily_rows, "day", "plays"),
        "weekly_listening": _serialize_series(weekly_rows, "week", "plays"),
        "hourly_listening": _serialize_series(hourly_rows, "hour", "plays"),
        "daily_genre": [
            {"day": str(day), "genre": genre, "plays": int(plays)}
            for day, genre, plays in daily_genre_rows
        ],
        "weekly_genre": [
            {"week": str(week), "genre": genre, "plays": int(plays)}
            for week, genre, plays in weekly_genre_rows
        ],
    }
