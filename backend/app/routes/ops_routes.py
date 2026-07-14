import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.user_session import UserSession
from ..models.listening_history import ListeningHistory
from ..services.metrics_service import get_metrics_snapshot
from ..services.artist_enrichment_service import enrich_artist_genres
from ..services.recommendation_service import backfill_missing_metadata, sync_listening_history
from ..services.spotify_service import INCREMENTAL_SYNC_MAX_TRACKS, fetch_recent_tracks, get_spotify_client, load_user_session
from ..time_utils import utcnow

router = APIRouter(prefix="/ops", tags=["Operations"])
logger = logging.getLogger(__name__)


@router.get("/health")
def health():
    # No DB query — Render pings this every ~10 s and a SELECT 1 on every ping
    # keeps Neon's compute awake 24/7, preventing auto-suspend.
    body = {
        "status": "ok",
        "time_utc": utcnow().isoformat(),
        "database": {"status": "unchecked"},
    }
    return JSONResponse(content=body, status_code=200)


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    """Readiness probe for operators; unlike liveness, this checks the DB."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.exception("readiness.database_failed")
        return JSONResponse(
            content={
                "status": "degraded",
                "time_utc": utcnow().isoformat(),
                "database": {"status": "error", "message": type(exc).__name__},
            },
            status_code=503,
        )
    return {
        "status": "ok",
        "time_utc": utcnow().isoformat(),
        "database": {"status": "ok"},
    }


@router.get("/metrics")
def metrics(request: Request):
    """Internal metrics endpoint — requires the same X-Cron-Secret used by the sync cron job."""
    expected = settings.CRON_SECRET or ""
    if not expected or request.headers.get("X-Cron-Secret", "") != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid cron secret")
    return get_metrics_snapshot()


@router.post("/sync-all")
def sync_all(request: Request, db: Session = Depends(get_db)):
    """Hourly cron endpoint — syncs listening history for every active user.

    Protected by X-Cron-Secret header matching the CRON_SECRET env var.
    Called by the Render cron job service defined in render.yaml.
    """
    expected = settings.CRON_SECRET or ""
    if not expected or request.headers.get("X-Cron-Secret", "") != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid cron secret")

    sessions = db.query(UserSession).all()
    total = len(sessions)
    synced = 0
    skipped = 0
    failed = 0

    for session_row in sessions:
        user_id = session_row.user_id
        try:
            session = load_user_session(db, user_id=user_id)
            token = session.get("token")
            if not token:
                skipped += 1
                logger.info("sync_all.skip user_id=%s reason=no_token", user_id)
                continue

            sp = get_spotify_client(token)
            checkpoint = db.query(func.max(ListeningHistory.played_at)).filter(ListeningHistory.user_id == user_id).scalar()
            tracks = fetch_recent_tracks(sp, max_tracks=INCREMENTAL_SYNC_MAX_TRACKS, since_played_at=checkpoint)
            sync_result = sync_listening_history(db, user_id, tracks)

            new_songs = sync_result.get("new_songs", 0)
            if new_songs > 0:
                backfill_missing_metadata(db, user_id=user_id, max_songs=new_songs + 10)

            enrich_artist_genres(db, sp, batch_size=50)

            synced += 1
            logger.info(
                "sync_all.ok user_id=%s new_songs=%s new_history=%s",
                user_id,
                new_songs,
                sync_result.get("new_history_rows", 0),
            )
        except Exception:
            failed += 1
            logger.exception("sync_all.failed user_id=%s", user_id)

    logger.info(
        "sync_all.done total=%s synced=%s skipped=%s failed=%s",
        total, synced, skipped, failed,
    )
    return {
        "message": "Sync complete",
        "total_users": total,
        "synced": synced,
        "skipped": skipped,
        "failed": failed,
    }


@router.post("/run-due-schedules")
def run_due_schedules(request: Request, limit: int = 50, db: Session = Depends(get_db)):
    expected = settings.CRON_SECRET or ""
    if not expected or request.headers.get("X-Cron-Secret", "") != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid cron secret")

    # Local import avoids coupling the route modules during application startup.
    from .playlist_routes import process_all_due_schedules

    result = process_all_due_schedules(db, limit=max(1, min(limit, 200)))
    logger.info("schedules.cron_done claimed=%s succeeded=%s failed=%s", result["claimed"], result["succeeded"], result["failed"])
    return {"message": "Due schedules processed", **result}
