import json
import logging
import threading
from functools import partial
from html import escape

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
import spotipy

from ..database import get_db, engine as _db_engine
from ..config import settings
from ..models.artist import Artist
from ..models.api_cache import ApiCache
from ..models.generated_playlist import GeneratedPlaylist
from ..models.job import Job
from ..models.listening_goal import ListeningGoal
from ..models.listening_history import ListeningHistory
from ..models.recommendation_feedback import RecommendationFeedback
from ..models.song import Song
from ..models.user_session import UserSession
from ..time_utils import utcnow_naive
from ..services.job_service import create_job, get_active_job, run_job, serialize_job
from ..services.rate_limit_service import enforce_rate_limit
from ..services import live_metrics_service
from ..services.spotify_service import (
    SESSION_COOKIE_NAME,
    clear_user_session,
    create_session_cookie_value,
    fetch_recent_tracks,
    get_spotify_oauth,
    get_spotify_client,
    get_session_cookie_options,
    get_stored_session_scope,
    load_request_user_session,
    load_user_session,
    missing_playlist_scopes,
    read_session_cookie_value,
    save_user_session,
)
from ..services.recommendation_service import (
    backfill_missing_metadata,
    sync_listening_history,
    _parse_played_at,
)

router = APIRouter(prefix="/user", tags=["User"])
logger = logging.getLogger(__name__)

IMPORT_RATE_LIMIT_NAMESPACE = "import_history_job"


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

        missing_scopes = missing_playlist_scopes(token_info)
        if missing_scopes:
            logger.warning("spotify.callback.missing_scopes missing=%s", ",".join(missing_scopes))
            return _login_popup_response(
                success=False,
                message=(
                    "Spotify login is missing playlist permissions. "
                    "Please approve playlist-modify-private and playlist-modify-public."
                ),
                frontend_origin=frontend_origin,
                status_code=403,
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
    user_id = session.get("user_id")
    # logged_in only requires a valid app session (cookie with user_id).
    # spotify_connected separately tracks whether the Spotify OAuth token is
    # still usable — it expires every hour and can fail to refresh. Keeping
    # these separate lets the app stay accessible even while Spotify reconnects.
    return {
        "logged_in": bool(user_id),
        "spotify_connected": bool(session.get("token") and user_id),
        "user_id": user_id,
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


@router.get("/spotify-auth-debug")
def spotify_auth_debug(request: Request, db: Session = Depends(get_db)):
    """Return non-secret Spotify auth/session diagnostics for the logged-in user."""
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    token = session.get("token")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    scope = get_stored_session_scope(db, user_id)
    spotify_user = {}
    spotify_error = None
    if token:
        try:
            spotify_user = get_spotify_client(token).current_user() or {}
        except Exception as exc:
            spotify_error = str(exc)[:700]

    return {
        "app_session_user_id": user_id,
        "spotify_connected": bool(token),
        "spotify_current_user_id": spotify_user.get("id"),
        "spotify_display_name": spotify_user.get("display_name"),
        "stored_scope": scope,
        "required_playlist_scopes": sorted(["playlist-modify-private", "playlist-modify-public"]),
        "missing_playlist_scopes_from_stored_scope": missing_playlist_scopes({"scope": scope}) if scope else None,
        "spotify_current_user_error": spotify_error,
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
    # Deleting the UserSession row discards the stored (encrypted) Spotify tokens
    # — our revocation mechanism, since load_user_session requires a matching row,
    # so any still-valid signed cookie is dead the moment the row is gone. This is
    # effectively "log out everywhere" (one session row per user). Users revoke the
    # Spotify grant itself from their Spotify account page.
    deleted = clear_user_session(db, requested_user_id) if requested_user_id else 0
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

    def _report_backfill_progress(*, current: int, total: int, scanned: int, updated: int, song):
        if song is not None:
            artist_name = song.artist.name if song.artist else "Unknown artist"
            song_label = f"{song.title} - {artist_name}"
            message = f"Enriching {current:,} / {max(1, total):,}: {song_label} ({updated:,} updated)"
        elif total <= 0:
            message = "No songs need metadata backfill"
        else:
            message = f"Enriching {current:,} / {max(1, total):,} ({updated:,} updated)"

        progress.update(
            current=int(current),
            total=max(1, int(total or 1)),
            message=message,
        )

    result = backfill_missing_metadata(
        db,
        user_id=user_id,
        max_songs=limit,
        include_partial=retry_partial,
        include_failed=retry_failed,
        progress_callback=_report_backfill_progress,
        progress_interval=5,
    )
    processed = int(result.get("processed") or result.get("total_candidates") or result.get("scanned") or 0)
    total = max(1, int(result.get("total_candidates") or processed or limit or 1))
    progress.update(
        current=processed,
        total=total,
        message=f"Backfill finished: {int(result.get('updated') or 0):,} updated",
    )
    return {
        "message": "Metadata backfill completed",
        "mode": {
            "retry_partial": retry_partial,
            "retry_failed": retry_failed,
        },
        "progress_current": processed,
        "progress_total": total,
        **result,
    }


_BULK_CHUNK = 500        # max items per IN-clause / artist batch
_HISTORY_CHUNK = 1000   # rows per bulk history INSERT (safe Postgres limit)


def _bulk_import_tracks(db: Session, user_id: str, tracks: list, progress) -> dict:
    """Bulk-optimised track import for large history files.

    Round-trip budget (10 k-track file, ~500 unique artists):
      Phase 1 – artists    : ceil(artists / 500)  ≈  1–3 queries
      Phase 2 – songs      : ceil(artists / 500)  ≈  1–3 queries   ← was 500+
      Phase 3 – history    : ceil(tracks  / 1000) ≈ 10 queries

    Old Phase 2 fired ONE query per unique artist (O(artists) round-trips).
    New Phase 2 loads all songs for all artists-in-the-file in bulk
    (O(artists/500) round-trips) and does the title/spotify matching in Python.
    """
    is_postgres = _db_engine.dialect.name == "postgresql"
    total = len(tracks)
    new_songs = 0
    new_history_rows = 0

    # ── Phase 1: Artists ─────────────────────────────────────────────────────
    progress.update(message=f"Syncing artists for {total:,} tracks…")

    unique_artist_names: set[str] = {
        t["artist"] for t in tracks if t.get("artist")
    }
    artist_map: dict[str, int] = {}  # name → artist_id

    name_list = list(unique_artist_names)
    for i in range(0, len(name_list), _BULK_CHUNK):
        chunk = name_list[i : i + _BULK_CHUNK]
        rows = db.query(Artist.name, Artist.id).filter(Artist.name.in_(chunk)).all()
        artist_map.update(rows)

    missing_names = unique_artist_names - artist_map.keys()
    new_artist_objs: list[Artist] = []
    for name in missing_names:
        a = Artist(name=name)
        db.add(a)
        new_artist_objs.append(a)

    if new_artist_objs:
        db.flush()  # populates .id on each new Artist in-memory
        for a in new_artist_objs:
            artist_map[a.name] = a.id

    db.commit()

    # ── Phase 2: Songs ───────────────────────────────────────────────────────
    # Load ALL songs for every artist present in the file using bulk
    # artist_id IN queries.  This replaces the old two-pass approach that fired
    # one query per unique artist for title-matching (O(artists) round-trips)
    # with O(ceil(artists/500)) round-trips and Python-side matching.
    progress.update(message=f"Checking library for {total:,} tracks…")

    spotify_song_map: dict[str, int] = {}   # spotify_id       → song_id
    title_song_map:  dict[tuple, int] = {}  # (title, artist_id) → song_id

    # 2a — load ALL songs for artists in the file (title + spotify_id matching)
    all_artist_ids = list(artist_map.values())
    for i in range(0, len(all_artist_ids), _BULK_CHUNK):
        chunk_aids = all_artist_ids[i : i + _BULK_CHUNK]
        rows = db.query(Song.spotify_id, Song.id, Song.title, Song.artist_id).filter(
            Song.artist_id.in_(chunk_aids),
            Song.is_deleted.is_(False),
        ).all()
        for sid, song_id, title, aid in rows:
            title_song_map[(title, aid)] = song_id
            if sid:
                spotify_song_map[sid] = song_id

    # 2b — spotify_id cross-check: catch songs that exist in the DB under a
    # DIFFERENT artist (e.g. artist name casing differs between two imports).
    # The artist_id lookup above would miss these, and Phase 2c would try to
    # INSERT a conflicting spotify_id → UniqueViolation.  Query without the
    # artist_id filter and without the is_deleted filter so we see every row
    # that holds the constraint key.
    all_file_spotify_ids = list({t["spotify_id"] for t in tracks if t.get("spotify_id")})
    for i in range(0, len(all_file_spotify_ids), _BULK_CHUNK):
        chunk_sids = all_file_spotify_ids[i : i + _BULK_CHUNK]
        rows = db.query(Song.spotify_id, Song.id).filter(
            Song.spotify_id.in_(chunk_sids),
        ).all()
        for sid, song_id in rows:
            if sid not in spotify_song_map:
                spotify_song_map[sid] = song_id  # don't create — it already exists

    # 2c — create songs that still don't exist
    seen_song_keys:    set[tuple] = set()
    seen_spotify_ids:  set[str]   = set()   # within-batch dedup by spotify_id
    new_song_meta: list[tuple[Song, str, int]] = []  # (obj, title, artist_id)

    for t in tracks:
        aid = artist_map.get(t.get("artist"))
        if not aid:
            continue
        sid = t.get("spotify_id")
        title = t.get("title") or ""
        key = (title, aid)

        if (sid and sid in spotify_song_map) or key in title_song_map:
            continue
        # Two tracks in the same file can share a spotify_id but have different
        # titles (e.g. "Song X" and "Song X (Remix)").  The key=(title, aid)
        # check above doesn't catch this, causing a UniqueViolation when both
        # are flushed in the same INSERT batch.  Skip the duplicate here.
        if sid and sid in seen_spotify_ids:
            continue
        if key in seen_song_keys:
            continue
        seen_song_keys.add(key)
        if sid:
            seen_spotify_ids.add(sid)

        song = Song(
            title=title,
            artist_id=aid,
            spotify_id=sid or None,
            image_url=t.get("image_url"),
            preview_url=t.get("preview_url"),
            discovery_source="history_sync",
            discovery_confidence=1.0,
            enrichment_status="pending",
            is_deleted=False,
        )
        db.add(song)
        new_song_meta.append((song, title, aid))
        new_songs += 1

    if new_song_meta:
        db.flush()  # populates .id on every new Song object in-memory
        for song, title, aid in new_song_meta:
            title_song_map[(title, aid)] = song.id
            if song.spotify_id:
                spotify_song_map[song.spotify_id] = song.id

    db.commit()
    progress.update(message=f"Added {new_songs:,} new songs. Importing listening history…")

    # ── Phase 3: Listening history ───────────────────────────────────────────
    rows_to_insert: list[dict] = []
    seen_history: set[tuple] = set()

    for t in tracks:
        aid = artist_map.get(t.get("artist"))
        if not aid:
            continue
        sid = t.get("spotify_id")
        title = t.get("title") or ""

        song_id = spotify_song_map.get(sid) if sid else None
        if not song_id:
            song_id = title_song_map.get((title, aid))
        if not song_id:
            continue

        played_at = _parse_played_at(t.get("played_at"))
        key = (song_id, played_at)
        if key in seen_history:
            continue
        seen_history.add(key)

        rows_to_insert.append({
            "user_id": user_id,
            "song_id": song_id,
            "played_at": played_at,
        })

    total_to_insert = len(rows_to_insert)
    for i in range(0, total_to_insert, _HISTORY_CHUNK):
        chunk = rows_to_insert[i : i + _HISTORY_CHUNK]

        if is_postgres:
            result = db.execute(
                pg_insert(ListeningHistory.__table__)
                .values(chunk)
                .on_conflict_do_nothing(
                    index_elements=["user_id", "song_id", "played_at"]
                )
            )
            new_history_rows += result.rowcount or 0
        else:
            # SQLite fallback used in tests — small data, correctness over speed
            for row in chunk:
                existing = (
                    db.query(ListeningHistory.id)
                    .filter_by(user_id=row["user_id"], song_id=row["song_id"], played_at=row["played_at"])
                    .first()
                )
                if not existing:
                    db.add(ListeningHistory(**row))
                    new_history_rows += 1

        imported = min(i + len(chunk), total)
        # No explicit db.commit() here — the INSERT is still in the open
        # transaction.  progress.update() calls db.commit() once, which flushes
        # both the INSERT rows and the progress fields in a single round-trip
        # (vs the old pattern of two separate commits per chunk).
        progress.update(
            current=imported,
            total=total,
            message=f"Importing {imported:,} / {total:,} tracks into history…",
        )

    if new_history_rows:
        live_metrics_service.increment(live_metrics_service.TRACKS_SYNCED, new_history_rows)

    existing_history_rows = total_to_insert - new_history_rows
    return {
        "new_songs": new_songs,
        "new_history_rows": new_history_rows,
        "existing_history_rows": existing_history_rows,
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


def _run_import_history_job(db, progress, *, user_id: str, tracks: list, entry_count: int = 0):
    """Run a bulk import for pre-parsed track dicts.

    ``tracks``      — output of _parse_extended_history (or equivalent
                      client-side logic): list of dicts with keys
                      title / artist / spotify_id / played_at / ms_played / skipped.
    ``entry_count`` — original number of raw entries (for reporting).
    """
    total_tracks = len(tracks)
    progress_total = max(1, total_tracks)

    progress.update(
        total=progress_total,
        current=0,
        message=f"Starting bulk import of {total_tracks:,} tracks…",
    )
    result = _bulk_import_tracks(db, user_id, tracks, progress)

    progress.update(
        current=progress_total,
        total=progress_total,
        message=(
            f"Done — {result['new_history_rows']:,} new history rows, "
            f"{result['new_songs']:,} new songs. "
            "Next: run Deduplication, then Metadata Enrichment."
        ),
    )

    return {
        "message": "Import complete. Run deduplication, then metadata enrichment.",
        "progress_current": progress_total,
        "progress_total": progress_total,
        "enrichment_queued": False,
        "next_step": "Run Deduplication → then Metadata Enrichment from Library Tools.",
        "entries_in_file": entry_count or total_tracks,
        "valid_tracks": total_tracks,
        **result,
    }


def _clear_previous_import_requests(db: Session, user_id: str):
    now = utcnow_naive()
    active_jobs = (
        db.query(Job)
        .filter(
            Job.user_id == user_id,
            Job.job_type == "import_history",
            Job.status.in_(("queued", "running")),
        )
        .all()
    )
    for job in active_jobs:
        job.status = "cancelled"
        job.finished_at = now
        job.message = "Cancelled because a newer import was started"
        db.add(job)
    db.flush()

    deleted_terminal = (
        db.query(Job)
        .filter(
            Job.user_id == user_id,
            Job.job_type == "import_history",
            Job.status.in_(("succeeded", "failed", "cancelled")),
        )
        .delete(synchronize_session=False)
    )

    cleared_rate_limits = (
        db.query(ApiCache)
        .filter(
            ApiCache.provider == "rate_limit",
            ApiCache.cache_key == f"rate_limit:{IMPORT_RATE_LIMIT_NAMESPACE}:{user_id}",
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return {
        "cancelled_active_imports": len(active_jobs),
        "deleted_previous_imports": int(deleted_terminal or 0),
        "cleared_import_rate_limits": int(cleared_rate_limits or 0),
    }


@router.post("/import-history/job")
async def import_history_job(
    request: Request,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    """Accept pre-processed tracks as a JSON body (preferred) or a raw
    Spotify history file as multipart/form-data (legacy).

    JSON body path (new, used by the frontend):
      POST /user/import-history/job
      Content-Type: application/json
      Body: [{title, artist, spotify_id, played_at, ms_played, skipped}, ...]

      The browser runs _parse_extended_history logic client-side before
      sending, cutting the payload from ~12 MB to ~1 MB and avoiding
      Render's proxy connection limit on large multipart bodies.

    Multipart path (legacy, kept for backward compatibility):
      POST /user/import-history/job
      Content-Type: multipart/form-data
      Field: file — any StreamingHistory_music_*.json from Spotify
    """
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    cleanup = _clear_previous_import_requests(db, user_id)
    enforce_rate_limit(request, namespace=IMPORT_RATE_LIMIT_NAMESPACE, user_id=user_id, limit=20, window_seconds=600)

    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        # ── New path: browser pre-processed tracks ───────────────────────────
        body = await request.body()
        if len(body) > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Payload too large (max 50 MB)")
        try:
            tracks = json.loads(body)
        except Exception:
            raise HTTPException(status_code=400, detail="Could not parse JSON body")
        if not isinstance(tracks, list):
            raise HTTPException(status_code=400, detail="Expected a JSON array of track objects")
        entry_count = len(tracks)

    elif "multipart/form-data" in content_type:
        # ── Legacy path: raw Spotify file upload ─────────────────────────────
        form = await request.form()
        file = form.get("file")
        if not file:
            raise HTTPException(status_code=400, detail="No file provided")
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
        entry_count = len(data)
        tracks = _parse_extended_history(data)

    else:
        raise HTTPException(
            status_code=415,
            detail="Expected application/json body or multipart/form-data file upload",
        )

    job = create_job(
        db,
        user_id=user_id,
        job_type="import_history",
        message=f"Queued import of {len(tracks):,} tracks",
        progress_total=max(1, len(tracks)),
    )
    background_tasks.add_task(
        run_job,
        job.id,
        partial(_run_import_history_job, user_id=user_id, tracks=tracks, entry_count=entry_count),
    )
    payload = serialize_job(job)
    payload["cleanup"] = cleanup
    return payload


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
