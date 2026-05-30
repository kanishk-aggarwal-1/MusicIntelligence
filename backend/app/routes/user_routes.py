import json
import logging
import threading
from functools import partial
from html import escape

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
import spotipy

from ..database import get_db
from ..config import settings
from ..models.generated_playlist import GeneratedPlaylist
from ..models.job import Job
from ..models.listening_goal import ListeningGoal
from ..models.listening_history import ListeningHistory
from ..models.recommendation_feedback import RecommendationFeedback
from ..models.song import Song
from ..models.user_session import UserSession
from ..services.job_service import create_job, get_active_job, run_job, serialize_job
from ..services.rate_limit_service import enforce_rate_limit
from ..services.spotify_service import (
    SESSION_COOKIE_NAME,
    create_session_cookie_value,
    fetch_recent_tracks,
    get_spotify_oauth,
    get_spotify_client,
    get_session_cookie_options,
    load_request_user_session,
    load_user_session,
    read_session_cookie_value,
    save_user_session,
)
from ..services.recommendation_service import backfill_missing_metadata, sync_listening_history

router = APIRouter(prefix="/user", tags=["User"])
logger = logging.getLogger(__name__)


def _allowed_frontend_origin(origin: str | None):
    cleaned = (origin or "").strip().rstrip("/")
    if cleaned and cleaned in settings.BACKEND_CORS_ORIGINS:
        return cleaned
    return None


def _frontend_message_origin(origin: str | None = None):
    if allowed := _allowed_frontend_origin(origin):
        return allowed
    # In development fall back to "*" so localhost vs 127.0.0.1 hostname
    # differences don't silently block the postMessage.
    if settings.APP_ENV != "production":
        return "*"
    origins = settings.BACKEND_CORS_ORIGINS or []
    return origins[0] if origins else "*"


def _login_popup_response(*, success: bool, message: str, frontend_origin: str, status_code: int = 200):
    event_type = "musicintel:login-success" if success else "musicintel:login-error"
    safe_message = escape(message)
    payload = json.dumps({"type": event_type, "message": message})
    target_origin = json.dumps(frontend_origin)
    close_script = "window.close();" if success else ""
    return HTMLResponse(
        f"""
    <html>
      <head><title>Spotify Login</title></head>
      <body style="font-family: sans-serif; padding: 16px;">
        <p>{safe_message}</p>
        <script>
          if (window.opener) {{
            window.opener.postMessage({payload}, {target_origin});
            {close_script}
          }}
        </script>
      </body>
    </html>
    """,
        status_code=status_code,
    )


@router.get("/login")
def login(request: Request):
    sp_oauth = get_spotify_oauth()
    frontend_origin = _allowed_frontend_origin(request.query_params.get("frontend_origin"))
    auth_url = sp_oauth.get_authorize_url(state=frontend_origin)
    logger.info("spotify.login.start frontend_origin=%s", frontend_origin)
    return RedirectResponse(auth_url)


@router.get("/callback", response_class=HTMLResponse)
def callback(request: Request, db: Session = Depends(get_db)):
    sp_oauth = get_spotify_oauth()
    frontend_origin = _frontend_message_origin(request.query_params.get("state"))
    error = request.query_params.get("error")
    if error:
        logger.warning("spotify.callback.denied error=%s", error)
        return _login_popup_response(
            success=False,
            message=f"Spotify login failed: {error}",
            frontend_origin=frontend_origin,
            status_code=400,
        )

    code = request.query_params.get("code")
    if not code:
        logger.warning("spotify.callback.missing_code")
        return _login_popup_response(
            success=False,
            message="Missing Spotify authorization code.",
            frontend_origin=frontend_origin,
            status_code=400,
        )

    try:
        token_info = sp_oauth.get_access_token(code, check_cache=False)
        if not token_info or "access_token" not in token_info:
            logger.warning("spotify.callback.exchange_empty")
            return _login_popup_response(
                success=False,
                message="Failed to exchange Spotify authorization code.",
                frontend_origin=frontend_origin,
                status_code=400,
            )

        access_token = token_info["access_token"]
        sp = spotipy.Spotify(auth=access_token)
        user = sp.current_user()
        save_user_session(db, user["id"], token_info=token_info)
    except Exception:
        logger.exception("spotify.callback.failed")
        return _login_popup_response(
            success=False,
            message="Spotify login failed while creating your session. Check Render environment variables and Spotify redirect settings.",
            frontend_origin=frontend_origin,
            status_code=500,
        )

    logger.info("spotify.callback.success user_id=%s frontend_origin=%s", user["id"], frontend_origin)
    response = _login_popup_response(
        success=True,
        message="Login successful. You can close this window.",
        frontend_origin=frontend_origin,
    )
    response.set_cookie(value=create_session_cookie_value(user["id"]), **get_session_cookie_options())
    return response


@router.get("/session")
def session_status(request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    return {
        "logged_in": bool(session.get("token") and session.get("user_id")),
        "user_id": session.get("user_id"),
    }


@router.get("/sync-status")
def sync_status(request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    user_song_ids = (
        db.query(ListeningHistory.song_id)
        .filter(ListeningHistory.user_id == user_id)
        .distinct()
        .subquery()
    )
    total_songs = (
        db.query(func.count(Song.id))
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(Song.is_deleted.is_(False))
        .scalar()
    ) or 0
    pending_count = (
        db.query(func.count(Song.id))
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(Song.is_deleted.is_(False), Song.enrichment_status == "pending")
        .scalar()
    ) or 0

    last_sync_job = (
        db.query(func.max(Job.finished_at))
        .filter(Job.user_id == user_id, Job.job_type == "sync_history", Job.status == "succeeded")
        .scalar()
    )
    last_import_job = (
        db.query(func.max(Job.finished_at))
        .filter(Job.user_id == user_id, Job.job_type == "import_history", Job.status == "succeeded")
        .scalar()
    )
    last_enriched = (
        db.query(func.max(Job.finished_at))
        .filter(Job.user_id == user_id, Job.job_type == "backfill_metadata", Job.status == "succeeded")
        .scalar()
    )

    last_synced = max([dt for dt in (last_sync_job, last_import_job) if dt], default=None)

    return {
        "last_synced_at": last_synced.isoformat() if last_synced else None,
        "last_enriched_at": last_enriched.isoformat() if last_enriched else None,
        "pending_enrichment_count": int(pending_count),
        "total_songs": int(total_songs),
    }


@router.get("/profile")
def get_profile(request: Request, db: Session = Depends(get_db)):
    """Return Spotify profile data for the logged-in user."""
    session = load_request_user_session(db, request)
    token = session.get("token")
    user_id = session.get("user_id")
    if not token or not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    spotify_user: dict = {}
    try:
        sp = get_spotify_client(token)
        spotify_user = sp.current_user() or {}
    except Exception:
        logger.warning("profile.spotify_fetch_failed user_id=%s", user_id)

    return {
        "user_id": user_id,
        "display_name": spotify_user.get("display_name") or user_id,
        "email": spotify_user.get("email"),
        "country": spotify_user.get("country"),
        "followers": (spotify_user.get("followers") or {}).get("total", 0),
        "images": spotify_user.get("images") or [],
        "product": spotify_user.get("product"),
        "spotify_url": (spotify_user.get("external_urls") or {}).get("spotify"),
    }


@router.delete("/delete-data")
def delete_user_data(request: Request, db: Session = Depends(get_db)):
    """Permanently delete all data associated with the logged-in user.

    Songs and artists are shared across users and are NOT deleted.
    The session cookie is cleared and the user is logged out.
    """
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    deleted: dict[str, int] = {}

    def _del(model, **filters):
        n = db.query(model).filter_by(**filters).delete(synchronize_session=False)
        deleted[model.__tablename__] = n

    _del(ListeningHistory,       user_id=user_id)
    _del(ListeningGoal,          user_id=user_id)
    _del(RecommendationFeedback, user_id=user_id)
    _del(Job,                    user_id=user_id)
    # Playlists cascade to tracks via the DB FK relationship
    _del(GeneratedPlaylist,      user_id=user_id)
    _del(UserSession,            user_id=user_id)

    db.commit()
    logger.info("delete_data.done user_id=%s rows=%s", user_id, deleted)

    response = JSONResponse({"message": "All user data deleted.", "deleted": deleted})
    cookie_opts = get_session_cookie_options()
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=cookie_opts["secure"],
        httponly=cookie_opts["httponly"],
        samesite=cookie_opts["samesite"],
    )
    return response


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    requested_user_id = read_session_cookie_value(request.cookies.get(SESSION_COOKIE_NAME))
    if not requested_user_id and settings.APP_ENV != "production":
        requested_user_id = (request.headers.get("X-User-Id") or "").strip() or None
    query = db.query(UserSession).filter(UserSession.user_id == requested_user_id) if requested_user_id else None
    deleted = query.delete(synchronize_session=False) if query is not None else 0
    db.commit()
    response = JSONResponse({"message": "Logged out", "deleted_sessions": deleted})
    cookie_opts = get_session_cookie_options()
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=cookie_opts["secure"],
        httponly=cookie_opts["httponly"],
        samesite=cookie_opts["samesite"],
    )
    return response


@router.post("/sync-history")
def sync_history(request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    token = session.get("token")
    user_id = session.get("user_id")

    if not token or not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")
    # Shared namespace with sync_history_job so both paths count against the same budget.
    enforce_rate_limit(request, namespace="spotify_sync", user_id=user_id, limit=10, window_seconds=60)

    sp = spotipy.Spotify(auth=token)
    tracks = fetch_recent_tracks(sp, max_tracks=50)
    sync_result = sync_listening_history(db, user_id, tracks)

    return {
        "message": "History synced",
        "fetched_items": len(tracks),
        **sync_result,
    }


def _pending_enrichment_count(db: Session, user_id: str):
    user_song_ids = (
        db.query(ListeningHistory.song_id)
        .filter(ListeningHistory.user_id == user_id)
        .distinct()
        .subquery()
    )
    return (
        db.query(func.count(Song.id))
        .join(user_song_ids, user_song_ids.c.song_id == Song.id)
        .filter(Song.is_deleted.is_(False), Song.enrichment_status == "pending")
        .scalar()
    ) or 0


def _queue_enrichment_job(db: Session, *, user_id: str, limit: int = 200):
    existing = get_active_job(db, user_id=user_id, job_type="backfill_metadata")
    if existing:
        return existing

    pending_count = int(_pending_enrichment_count(db, user_id))
    if pending_count <= 0:
        return None

    job = create_job(
        db,
        user_id=user_id,
        job_type="backfill_metadata",
        message="Queued tag and genre enrichment",
        progress_total=min(limit, pending_count),
    )
    thread = threading.Thread(
        target=run_job,
        args=(job.id, partial(_run_backfill_job, user_id=user_id, limit=limit, retry_partial=False, retry_failed=False)),
        daemon=True,
    )
    thread.start()
    return job


def _run_sync_history_job(db: Session, progress, *, user_id: str):
    session = load_user_session(db, user_id=user_id)
    token = session.get("token")
    if not token:
        raise RuntimeError("User not logged in")

    progress.update(total=3, current=0, message="Fetching recent Spotify plays")
    sp = get_spotify_client(token)
    tracks = fetch_recent_tracks(sp, max_tracks=50)

    progress.update(current=1, message="Syncing listening history")
    sync_result = sync_listening_history(db, user_id, tracks)

    progress.update(current=2, message="Finalizing sync")
    enrichment_job = _queue_enrichment_job(db, user_id=user_id, limit=200)
    return {
        "message": "History sync completed",
        "fetched_items": len(tracks),
        "progress_current": 3,
        "progress_total": 3,
        "enrichment_queued": bool(enrichment_job),
        "enrichment_job_id": enrichment_job.id if enrichment_job else None,
        **sync_result,
    }


@router.post("/sync-history/job")
def sync_history_job(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    # Check for a running job first — returning it is free and must not burn tokens.
    existing = get_active_job(db, user_id=user_id, job_type="sync_history")
    if existing:
        return serialize_job(existing)

    # Shared namespace with /sync-history so the two paths share one budget.
    enforce_rate_limit(request, namespace="spotify_sync", user_id=user_id, limit=10, window_seconds=60)

    job = create_job(db, user_id=user_id, job_type="sync_history", message="Queued recent-history sync", progress_total=3)
    background_tasks.add_task(run_job, job.id, partial(_run_sync_history_job, user_id=user_id))
    return serialize_job(job)


@router.post("/backfill-metadata")
def backfill_metadata(
    request: Request,
    limit: int = 500,
    retry_partial: bool = False,
    retry_failed: bool = False,
    db: Session = Depends(get_db),
):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")
    enforce_rate_limit(request, namespace="backfill", user_id=user_id, limit=5, window_seconds=60)

    result = backfill_missing_metadata(
        db,
        user_id=user_id,
        max_songs=limit,
        include_partial=retry_partial,
        include_failed=retry_failed,
    )

    return {
        "message": "Metadata backfill completed",
        "mode": {
            "retry_partial": retry_partial,
            "retry_failed": retry_failed,
        },
        **result,
    }


def _run_backfill_job(db: Session, progress, *, user_id: str, limit: int, retry_partial: bool, retry_failed: bool):
    progress.update(total=max(1, int(limit)), current=0, message="Scanning songs for metadata backfill")
    result = backfill_missing_metadata(
        db,
        user_id=user_id,
        max_songs=limit,
        include_partial=retry_partial,
        include_failed=retry_failed,
    )
    progress.update(
        current=int(result.get("scanned") or 0),
        total=max(1, int(result.get("scanned") or limit or 1)),
        message="Backfill finished",
    )
    return {
        "message": "Metadata backfill completed",
        "mode": {
            "retry_partial": retry_partial,
            "retry_failed": retry_failed,
        },
        "progress_current": int(result.get("scanned") or 0),
        "progress_total": max(1, int(result.get("scanned") or limit or 1)),
        **result,
    }


def _parse_extended_history(data: list) -> list:
    """Convert Spotify extended streaming history entries into sync-compatible track dicts."""
    tracks = []
    for entry in data:
        # Skip podcast episodes and entries with no track name
        if entry.get("episode_name") or not entry.get("master_metadata_track_name"):
            continue

        ms_played = entry.get("ms_played") or 0

        # Ignore plays shorter than 30 seconds — accidental starts, previews
        if ms_played < 30_000:
            continue

        reason_end = (entry.get("reason_end") or "").lower()
        skipped = reason_end in ("fwdbtn", "endplay")

        spotify_uri = entry.get("spotify_track_uri") or ""
        spotify_id = spotify_uri.split(":")[-1] if spotify_uri.startswith("spotify:track:") else None

        tracks.append({
            "title": entry.get("master_metadata_track_name"),
            "artist": entry.get("master_metadata_album_artist_name"),
            "spotify_id": spotify_id,
            "played_at": entry.get("ts"),
            "ms_played": ms_played,
            "skipped": skipped,
        })
    return tracks


def _run_import_history_job(db, progress, *, user_id: str, data: list):
    progress.update(total=3, current=0, message="Parsing tracks from Spotify history file")
    tracks = _parse_extended_history(data)

    progress.update(current=1, message=f"Importing {len(tracks):,} tracks into library")
    result = sync_listening_history(db, user_id, tracks, enrich_inline=False)

    progress.update(current=2, message="Backfilling Last.fm metadata for new songs")
    new_songs = result.get("new_songs", 0)
    if new_songs > 0:
        backfill_missing_metadata(db, user_id=user_id, max_songs=new_songs + 50)

    return {
        "message": "Import complete",
        "entries_in_file": len(data),
        "valid_tracks": len(tracks),
        **result,
    }


@router.post("/import-history/job")
async def import_history_job(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db=Depends(get_db),
):
    """Upload a Spotify Extended Streaming History JSON file to bulk-import listening history.

    Download your data at: https://www.spotify.com/account/privacy/
    Upload any of the StreamingHistory_music_*.json files.
    """
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")
    enforce_rate_limit(request, namespace="import_history_job", user_id=user_id, limit=3, window_seconds=600)

    if file.content_type not in ("application/json", "text/plain", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Expected a JSON file")

    content = await file.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 100 MB)")

    try:
        data = json.loads(content)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse JSON file")

    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail="Expected a JSON array of history entries")

    job = create_job(
        db,
        user_id=user_id,
        job_type="import_history",
        message=f"Queued import of {len(data):,} history entries",
        progress_total=3,
    )
    background_tasks.add_task(
        run_job,
        job.id,
        partial(_run_import_history_job, user_id=user_id, data=data),
    )
    return serialize_job(job)


@router.post("/backfill-metadata/job")
def backfill_metadata_job(
    request: Request,
    background_tasks: BackgroundTasks,
    limit: int = 500,
    retry_partial: bool = False,
    retry_failed: bool = False,
    db: Session = Depends(get_db),
):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    # Return existing job without consuming a rate-limit token.
    existing = get_active_job(db, user_id=user_id, job_type="backfill_metadata")
    if existing:
        return serialize_job(existing)

    # Shared namespace with /backfill-metadata so both paths share one budget.
    enforce_rate_limit(request, namespace="backfill", user_id=user_id, limit=5, window_seconds=60)

    job = create_job(
        db,
        user_id=user_id,
        job_type="backfill_metadata",
        message="Queued metadata backfill",
        progress_total=max(1, min(limit, 5000)),
    )
    background_tasks.add_task(
        run_job,
        job.id,
        partial(
            _run_backfill_job,
            user_id=user_id,
            limit=limit,
            retry_partial=retry_partial,
            retry_failed=retry_failed,
        ),
    )
    return serialize_job(job)
