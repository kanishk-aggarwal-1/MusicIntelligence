from functools import partial

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
import spotipy

from ..database import get_db
from ..services.job_service import create_job, run_job, serialize_job
from ..services.spotify_service import (
    fetch_recent_tracks,
    get_spotify_oauth,
    get_spotify_client,
    load_request_user_session,
    load_user_session,
    save_user_session,
)
from ..services.recommendation_service import backfill_missing_metadata, sync_listening_history

router = APIRouter(prefix="/user", tags=["User"])


@router.get("/login")
def login():
    sp_oauth = get_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    return RedirectResponse(auth_url)


@router.get("/callback", response_class=HTMLResponse)
def callback(request: Request, db: Session = Depends(get_db)):
    sp_oauth = get_spotify_oauth()
    error = request.query_params.get("error")
    if error:
        raise HTTPException(status_code=400, detail=f"Spotify login failed: {error}")

    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing Spotify authorization code")

    token_info = sp_oauth.get_access_token(code)
    if not token_info or "access_token" not in token_info:
        raise HTTPException(status_code=400, detail="Failed to exchange Spotify authorization code")

    access_token = token_info["access_token"]
    sp = spotipy.Spotify(auth=access_token)
    user = sp.current_user()
    save_user_session(db, user["id"], token_info=token_info)

    return """
    <html>
      <head><title>Login Complete</title></head>
      <body style=\"font-family: sans-serif; padding: 16px;\">
        <p>Login successful. You can close this window.</p>
        <script>
          try { window.close(); } catch (e) {}
        </script>
      </body>
    </html>
    """


@router.get("/session")
def session_status(request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    return {
        "logged_in": bool(session.get("token") and session.get("user_id")),
        "user_id": session.get("user_id"),
    }


@router.post("/sync-history")
def sync_history(request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    token = session.get("token")
    user_id = session.get("user_id")

    if not token or not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    sp = spotipy.Spotify(auth=token)
    tracks = fetch_recent_tracks(sp, max_tracks=50)
    sync_result = sync_listening_history(db, user_id, tracks)

    return {
        "message": "History synced",
        "fetched_items": len(tracks),
        **sync_result,
    }


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
    return {
        "message": "History sync completed",
        "fetched_items": len(tracks),
        "progress_current": 3,
        "progress_total": 3,
        **sync_result,
    }


@router.post("/sync-history/job")
def sync_history_job(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

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
