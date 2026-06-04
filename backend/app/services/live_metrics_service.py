"""Persistent, cumulative live-traffic counters backed by Postgres.

Unlike the in-process ``metrics_service`` (which resets on every restart), these
counters survive restarts/cold starts. Every increment is an atomic UPSERT in
its own short transaction so it never interferes with the request's DB session,
and all writes are best-effort: a metrics failure must never break real traffic.

Only non-sensitive aggregates are stored — counts, never tokens or PII.
"""
import logging

from sqlalchemy import select

from ..database import SessionLocal, engine
from ..models.metric_counter import MetricCounter
from ..time_utils import utcnow_naive

logger = logging.getLogger(__name__)

# Canonical counter names (kept in one place so /stats and instrumentation agree).
CACHE_HITS = "cache.hits"
CACHE_MISSES = "cache.misses"
SPOTIFY_CALLS = "external.spotify_calls"
LASTFM_CALLS = "external.lastfm_calls"
TRACKS_SYNCED = "tracks.synced"
TRACKS_ENRICHED = "tracks.enriched"
PLAYLISTS_GENERATED = "playlists.generated"
PLAYLIST_TRACKS_REQUESTED = "playlist.tracks_requested"
PLAYLIST_TRACKS_RESOLVED = "playlist.tracks_resolved"

ALL_COUNTERS = [
    CACHE_HITS,
    CACHE_MISSES,
    SPOTIFY_CALLS,
    LASTFM_CALLS,
    TRACKS_SYNCED,
    TRACKS_ENRICHED,
    PLAYLISTS_GENERATED,
    PLAYLIST_TRACKS_REQUESTED,
    PLAYLIST_TRACKS_RESOLVED,
]


def _upsert_increment(db, name: str, amount: int):
    """Atomic `INSERT ... ON CONFLICT DO UPDATE value = value + amount`.

    Works on both PostgreSQL (production) and SQLite (tests/CI)."""
    dialect = engine.dialect.name
    table = MetricCounter.__table__
    now = utcnow_naive()

    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as _insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as _insert
    else:
        # Generic fallback: read-modify-write (no native upsert).
        row = db.execute(select(MetricCounter).where(MetricCounter.name == name)).scalar_one_or_none()
        if row is None:
            db.add(MetricCounter(name=name, value=int(amount), updated_at=now))
        else:
            row.value = int(row.value or 0) + int(amount)
            row.updated_at = now
        return

    stmt = _insert(table).values(name=name, value=int(amount), updated_at=now)
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.name],
        set_={"value": table.c.value + int(amount), "updated_at": now},
    )
    db.execute(stmt)


def increment(name: str, amount: int = 1):
    """Increment one counter by `amount` (default 1). Best-effort / fail-open —
    a metrics failure (incl. failing to even open a session) never propagates."""
    if amount == 0:
        return
    db = None
    try:
        db = SessionLocal()
        _upsert_increment(db, name, amount)
        db.commit()
    except Exception:
        if db is not None:
            db.rollback()
        logger.debug("live_metrics.increment_failed name=%s", name, exc_info=True)
    finally:
        if db is not None:
            db.close()


def increment_many(amounts: dict[str, int]):
    """Increment several counters in a single transaction. Best-effort / fail-open."""
    items = [(n, int(a)) for n, a in (amounts or {}).items() if a]
    if not items:
        return
    db = None
    try:
        db = SessionLocal()
        for name, amount in items:
            _upsert_increment(db, name, amount)
        db.commit()
    except Exception:
        if db is not None:
            db.rollback()
        logger.debug("live_metrics.increment_many_failed", exc_info=True)
    finally:
        if db is not None:
            db.close()


def get_counters() -> dict[str, int]:
    """Return all counters as a name->value dict (missing counters read as 0)."""
    counters = {name: 0 for name in ALL_COUNTERS}
    last_updated = None
    db = None
    try:
        db = SessionLocal()
        for row in db.execute(select(MetricCounter)).scalars().all():
            counters[row.name] = int(row.value or 0)
            if row.updated_at and (last_updated is None or row.updated_at > last_updated):
                last_updated = row.updated_at
    except Exception:
        logger.debug("live_metrics.get_counters_failed", exc_info=True)
    finally:
        if db is not None:
            db.close()
    counters["_updated_at"] = last_updated.isoformat() if last_updated else None
    return counters


def _pct(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def build_stats() -> dict:
    """Shape the raw counters into the public, non-sensitive /stats payload."""
    c = get_counters()
    hits = c[CACHE_HITS]
    misses = c[CACHE_MISSES]
    cache_total = hits + misses
    requested = c[PLAYLIST_TRACKS_REQUESTED]
    resolved = c[PLAYLIST_TRACKS_RESOLVED]

    hit_rate = _pct(hits, cache_total)

    return {
        "cache": {
            "hits": hits,
            "misses": misses,
            "lookups": cache_total,
            "hit_rate_pct": hit_rate,
            # Each cache hit is an external API call that did NOT have to be made.
            "api_calls_saved": hits,
            "api_calls_saved_pct": hit_rate,
        },
        "external_api_calls": {
            "spotify": c[SPOTIFY_CALLS],
            "lastfm": c[LASTFM_CALLS],
            "total": c[SPOTIFY_CALLS] + c[LASTFM_CALLS],
        },
        "tracks": {
            "synced": c[TRACKS_SYNCED],
            "enriched": c[TRACKS_ENRICHED],
        },
        "playlists": {
            "generated": c[PLAYLISTS_GENERATED],
            "tracks_requested": requested,
            "tracks_resolved": resolved,
            "resolution_rate_pct": _pct(resolved, requested),
        },
        "updated_at": c["_updated_at"],
        "note": "Cumulative since first deploy. Persisted in Postgres; survives restarts.",
    }
