import logging
import time
from math import ceil
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from spotipy.exceptions import SpotifyException

from ..database import get_db
from ..models.generated_playlist import GeneratedPlaylist
from ..models.generated_playlist_track import GeneratedPlaylistTrack
from ..models.listening_history import ListeningHistory
from ..models.song import Song
from ..services.generated_playlist_service import (
    ALGORITHM_VERSION,
    build_playlist_name,
    create_playlist_preview_record,
    get_generated_playlist,
    list_generated_playlists,
    mark_generated_playlist_created,
    serialize_generated_playlist,
)
from ..services.playlist_schedule_service import (
    MAX_SCHEDULES_PER_USER,
    VALID_CADENCES,
    count_schedules,
    create_schedule,
    delete_schedule,
    due_schedules,
    get_schedule,
    list_schedules,
    mark_ran,
    serialize_schedule,
)
from ..services import live_metrics_service
from ..services.rate_limit_service import enforce_rate_limit
from ..services.recommendation_service import recommend_songs
from ..services.spotify_service import (
    clear_user_session,
    create_playlist,
    get_missing_stored_playlist_scopes,
    get_spotify_client,
    load_request_user_session,
    load_user_session,
    resolve_track_id,
)
from ..time_utils import utcnow

router = APIRouter(prefix="/playlists", tags=["Playlists"])
logger = logging.getLogger(__name__)


class PlaylistGeneratePayload(BaseModel):
    min_known_ratio: float = 0.6
    diversity: float = 0.5
    familiarity: float = 0.5
    max_tracks: int = 30
    name: str | None = None
    context_type: str | None = None


class PlaylistNamePayload(BaseModel):
    name: str


class ScheduleCreatePayload(BaseModel):
    cadence: str = "weekly"  # 'daily' | 'weekly'
    name: str | None = None
    context_type: str | None = None
    min_known_ratio: float = 0.6
    diversity: float = 0.5
    familiarity: float = 0.5
    max_tracks: int = 30


CONTEXT_DEFAULTS = {
    "focus": {"diversity": 0.35, "familiarity": 0.7, "max_tracks": 30},
    "workout": {"diversity": 0.45, "familiarity": 0.75, "max_tracks": 30},
    "late-night": {"diversity": 0.55, "familiarity": 0.55, "max_tracks": 30},
    "chill": {"diversity": 0.6, "familiarity": 0.5, "max_tracks": 30},
}


def _dedupe_keep_order(values):
    seen = set()
    out = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _fallback_top_listened_ids(db, user_id, limit=50):
    rows = (
        db.query(Song.spotify_id, func.count(ListeningHistory.id).label("plays"))
        .join(ListeningHistory, ListeningHistory.song_id == Song.id)
        .filter(
            ListeningHistory.user_id == user_id,
            Song.spotify_id.is_not(None),
            Song.is_deleted.is_(False),
        )
        .group_by(Song.spotify_id)
        .order_by(func.count(ListeningHistory.id).desc())
        .limit(limit)
        .all()
    )
    return [r[0] for r in rows if r[0]]


def _apply_quality_controls(details, diversity: float, familiarity: float):
    diversity = max(0.0, min(diversity, 1.0))
    familiarity = max(0.0, min(familiarity, 1.0))

    if not details:
        return details

    details = details[:]

    if diversity >= 0.6:
        grouped = {}
        for item in details:
            artist = item["song"].artist.name if item["song"].artist else "unknown"
            grouped.setdefault(artist, []).append(item)

        interleaved = []
        while grouped:
            for key in list(grouped.keys()):
                bucket = grouped[key]
                if bucket:
                    interleaved.append(bucket.pop(0))
                if not bucket:
                    grouped.pop(key, None)
        details = interleaved

    if familiarity >= 0.6:
        details.sort(key=lambda x: (x["song"].spotify_id is None, -x["score"]))

    return details


def _enforce_known_ratio(details, max_tracks: int, min_known_ratio: float):
    if not details:
        return details

    target_ratio = max(0.0, min(min_known_ratio, 1.0))
    if target_ratio <= 0:
        return details

    desired_known = min(max_tracks, ceil(max_tracks * target_ratio))
    known = [item for item in details if item["song"].spotify_id]

    if len(known) < desired_known:
        return details

    reordered = known[:desired_known]
    for item in details:
        if item in reordered:
            continue
        reordered.append(item)
    return reordered


def _artist_name(item):
    song = item.get("song") if isinstance(item, dict) else None
    artist = song.artist if song else None
    return (artist.name if artist else "unknown").strip().lower()


def _artist_cap_for_diversity(diversity: float):
    if diversity >= 0.75:
        return 1
    if diversity >= 0.45:
        return 2
    return 3


def _cap_artist_repetition(details, max_tracks: int, diversity: float):
    if not details or max_tracks <= 0:
        return details

    max_per_artist = _artist_cap_for_diversity(diversity)

    selected = []
    deferred = []
    artist_counts = {}

    for item in details:
        artist = _artist_name(item)
        if artist_counts.get(artist, 0) < max_per_artist:
            selected.append(item)
            artist_counts[artist] = artist_counts.get(artist, 0) + 1
        else:
            deferred.append(item)
        if len(selected) >= max_tracks:
            break

    if len(selected) < max_tracks:
        for item in deferred:
            selected.append(item)
            if len(selected) >= max_tracks:
                break

    selected_ids = {id(item) for item in selected}
    selected.extend(item for item in details if id(item) not in selected_ids)
    return selected


def _recent_generated_song_ids(db: Session, user_id: str, limit: int = 5):
    recent_playlist_ids = [
        row[0]
        for row in (
            db.query(GeneratedPlaylist.id)
            .filter(GeneratedPlaylist.user_id == user_id)
            .order_by(GeneratedPlaylist.created_at.desc())
            .limit(max(1, limit))
            .all()
        )
    ]
    if not recent_playlist_ids:
        return set()

    return {
        row[0]
        for row in (
            db.query(GeneratedPlaylistTrack.song_id)
            .filter(GeneratedPlaylistTrack.generated_playlist_id.in_(recent_playlist_ids))
            .all()
        )
    }


def _deprioritize_recent_playlist_repeats(details, recent_song_ids: set[int], max_tracks: int):
    if not details or not recent_song_ids:
        return details

    fresh = [item for item in details if item["song"].id not in recent_song_ids]
    repeated = [item for item in details if item["song"].id in recent_song_ids]
    if len(fresh) >= max_tracks:
        return fresh + repeated
    return details


def _playlist_quality_notes(*, diversity: float, recent_song_ids: set[int]):
    artist_cap = _artist_cap_for_diversity(diversity)
    notes = [
        f"Artist variety guardrail prefers at most {artist_cap} track{'s' if artist_cap != 1 else ''} per artist when alternatives exist.",
    ]
    if recent_song_ids:
        notes.append("Recent playlist repeat guardrail prefers songs not used in your last 5 generated playlists.")
    else:
        notes.append("Recent playlist repeat guardrail will activate after you have generated playlist history.")
    return notes


def _playlist_preview_summary(serialized_playlist: dict, quality_notes: list[str]):
    summary = serialized_playlist.get("summary") or {}
    tags = summary.get("dominant_tags") or []
    genres = summary.get("dominant_genres") or []
    artist_count = summary.get("artist_count") or 0

    parts = []
    if genres:
        parts.append(f"Built around {', '.join(genres[:2])}")
    elif tags:
        parts.append(f"Built around {', '.join(tags[:2])}")
    else:
        parts.append("Built from your current taste profile")

    if artist_count:
        parts.append(f"{artist_count} artists for variety")

    if quality_notes:
        parts.append("with guardrails for freshness and balance")

    return " - ".join(parts) + "."


def _build_playlist_warnings(details, max_tracks, created_track_count=0, spotify_rate_limited=False):
    warnings = []
    if not details:
        warnings.append("No recommendation candidates were produced from the current library.")
    if created_track_count and created_track_count < max_tracks:
        warnings.append(f"Only {created_track_count} Spotify-resolvable tracks were available for a target of {max_tracks}.")
    if created_track_count == 0:
        warnings.append("No Spotify-resolvable tracks were available for creation.")
    if spotify_rate_limited:
        warnings.append("Spotify search rate limit was hit during this request, so track resolution was cut short.")
    return warnings


def _spotify_error_detail(exc, *, prefix: str):
    reason = getattr(exc, "reason", None)
    status = getattr(exc, "http_status", None)
    raw = str(exc)
    parts = [prefix]
    if status:
        parts.append(f"Spotify status {status}.")
    if reason:
        parts.append(f"Reason: {reason}.")
    if raw:
        parts.append(raw[:700])
    return " ".join(parts)


def _looks_like_scope_error(exc):
    text = f"{getattr(exc, 'reason', '')} {exc}".lower()
    return (
        "scope" in text
        or "permission" in text
        or "playlist-modify-private" in text
        or "playlist-modify-public" in text
    )

def _resolve_playlist_track_ids(db, sp, generated_playlist: GeneratedPlaylist, user_id: str):
    resolved_now = 0
    track_ids = []
    rate_limited = False

    sorted_tracks = sorted(generated_playlist.tracks, key=lambda item: item.position)
    for preview_track in sorted_tracks:
        song = preview_track.song
        if not song:
            continue
        track_id = song.spotify_id
        artist_name = song.artist.name if song.artist else None

        if not track_id:
            try:
                track_id = resolve_track_id(sp, song.title, artist_name)
            except Exception as exc:
                status = getattr(exc, "http_status", None)
                if status == 401:
                    logger.info("playlist.resolve.token_expired title=%s artist=%s", song.title, artist_name)
                    session = load_user_session(db, user_id=user_id)
                    refreshed_token = session.get("token")
                    if not refreshed_token:
                        raise
                    sp = get_spotify_client(refreshed_token)
                    track_id = resolve_track_id(sp, song.title, artist_name)
                elif status == 429:
                    logger.warning("playlist.resolve.rate_limited title=%s artist=%s", song.title, artist_name)
                    rate_limited = True
                    break
                else:
                    raise
            if track_id:
                song.spotify_id = track_id
                resolved_now += 1

        if track_id:
            track_ids.append(track_id)

    if resolved_now:
        db.commit()

    deduped = _dedupe_keep_order(track_ids)
    # Playlist resolution rate = resolved Spotify URIs / tracks requested.
    requested = sum(1 for t in sorted_tracks if t.song)
    live_metrics_service.increment_many({
        live_metrics_service.PLAYLIST_TRACKS_REQUESTED: requested,
        live_metrics_service.PLAYLIST_TRACKS_RESOLVED: len(deduped),
    })

    return deduped, resolved_now, rate_limited


def _create_playlist_with_refresh(db, sp, user_id: str, name: str, track_ids):
    missing_scopes = get_missing_stored_playlist_scopes(db, user_id)
    if missing_scopes:
        clear_user_session(db, user_id)
        raise HTTPException(
            status_code=403,
            detail=(
                "Your stored Spotify login is missing playlist permissions. "
                "Log in again and approve playlist-modify-private and playlist-modify-public scopes."
            ),
        )

    try:
        return create_playlist(sp, user_id, track_ids, name=name)
    except Exception as exc:
        if getattr(exc, "http_status", None) != 401:
            if isinstance(exc, SpotifyException) and getattr(exc, "http_status", None) == 403:
                if _looks_like_scope_error(exc):
                    clear_user_session(db, user_id)
                raise HTTPException(
                    status_code=403,
                    detail=_spotify_error_detail(exc, prefix="Spotify refused playlist creation or track insertion."),
                ) from exc
            raise
        logger.info("playlist.create.token_expired user_id=%s", user_id)
        session = load_user_session(db, user_id=user_id)
        refreshed_token = session.get("token")
        if not refreshed_token:
            raise
        refreshed_sp = get_spotify_client(refreshed_token)
        try:
            return create_playlist(refreshed_sp, user_id, track_ids, name=name)
        except Exception as refresh_exc:
            if isinstance(refresh_exc, SpotifyException) and getattr(refresh_exc, "http_status", None) == 403:
                if _looks_like_scope_error(refresh_exc):
                    clear_user_session(db, user_id)
                raise HTTPException(
                    status_code=403,
                    detail=_spotify_error_detail(refresh_exc, prefix="Spotify refused playlist creation or track insertion after token refresh."),
                ) from refresh_exc
            raise


def _build_preview(db: Session, user_id: str, payload: PlaylistGeneratePayload):
    started = time.perf_counter()
    requested_tracks = max(1, min(payload.max_tracks, 100))
    candidate_limit = max(30, min(requested_tracks * 4, 150))

    recommendation_result = recommend_songs(
        db,
        user_id,
        return_details=True,
        min_known_ratio=payload.min_known_ratio,
        include_discovery_summary=True,
        allow_discovery=False,
        context_type=payload.context_type,
        limit=candidate_limit,
    )

    details = recommendation_result["items"]
    details = _apply_quality_controls(details, payload.diversity, payload.familiarity)
    details = _enforce_known_ratio(details, requested_tracks, payload.min_known_ratio)
    details = _cap_artist_repetition(details, requested_tracks, payload.diversity)
    recent_song_ids = _recent_generated_song_ids(db, user_id, limit=5)
    details = _deprioritize_recent_playlist_repeats(details, recent_song_ids, requested_tracks)
    selected = details[:requested_tracks]

    request_params = {
        "min_known_ratio": payload.min_known_ratio,
        "diversity": payload.diversity,
        "familiarity": payload.familiarity,
        "max_tracks": requested_tracks,
        "context_type": payload.context_type,
        "generated_at_utc": utcnow().isoformat(),
        "recent_playlist_repeat_guard": bool(recent_song_ids),
    }

    record = create_playlist_preview_record(
        db,
        user_id=user_id,
        name=build_playlist_name(selected, context_type=payload.context_type, explicit_name=payload.name),
        context_type=payload.context_type,
        request_params=request_params,
        candidate_pool_size=len(details),
        items=selected,
        algorithm_version=recommendation_result.get("algorithm_version") or ALGORITHM_VERSION,
    )

    serialized = serialize_generated_playlist(record, include_tracks=True)
    resolved_count = sum(1 for item in selected if item["song"].spotify_id)
    warnings = _build_playlist_warnings(selected, requested_tracks, created_track_count=resolved_count)
    quality_notes = _playlist_quality_notes(diversity=payload.diversity, recent_song_ids=recent_song_ids)

    return {
        "message": "Playlist preview generated",
        "generated_playlist": serialized,
        "recommendation_candidates": len(details),
        "warnings": warnings,
        "preview_summary": _playlist_preview_summary(serialized, quality_notes),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "quality_controls": {
            "min_known_ratio": payload.min_known_ratio,
            "diversity": payload.diversity,
            "familiarity": payload.familiarity,
            "max_tracks": requested_tracks,
            "artist_cap": _artist_cap_for_diversity(payload.diversity),
            "recent_repeat_guard_active": bool(recent_song_ids),
            "notes": quality_notes,
        },
    }


@router.get("/generated")
def generated_history(request: Request, limit: int = 30, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    records = list_generated_playlists(db, user_id=user_id, limit=limit)
    return {"items": [serialize_generated_playlist(record, include_tracks=False) for record in records]}


@router.get("/generated/{generated_playlist_id}")
def generated_detail(generated_playlist_id: int, request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    record = get_generated_playlist(db, generated_playlist_id=generated_playlist_id, user_id=user_id)
    if not record:
        raise HTTPException(status_code=404, detail="Generated playlist not found")

    return serialize_generated_playlist(record, include_tracks=True)


@router.patch("/generated/{generated_playlist_id}/name")
def update_generated_name(generated_playlist_id: int, payload: PlaylistNamePayload, request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Playlist name is required")
    if len(name) > 120:
        raise HTTPException(status_code=400, detail="Playlist name must be 120 characters or fewer")

    record = get_generated_playlist(db, generated_playlist_id=generated_playlist_id, user_id=user_id)
    if not record:
        raise HTTPException(status_code=404, detail="Generated playlist not found")

    record.name = name
    db.add(record)
    db.commit()
    db.refresh(record)
    return serialize_generated_playlist(record, include_tracks=True)


@router.post("/preview")
def preview(payload: PlaylistGeneratePayload, request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    return _build_preview(db, user_id, payload)


@router.post("/generated/{generated_playlist_id}/create")
def create_from_preview(generated_playlist_id: int, request: Request, db: Session = Depends(get_db)):
    started = time.perf_counter()
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    token = session.get("token")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")
    if not token:
        raise HTTPException(status_code=401, detail="spotify_token_expired")

    # Pushing to Spotify resolves many track IDs and creates a playlist — cap it
    # to protect the Spotify API quota from rapid repeated saves.
    enforce_rate_limit(request, namespace="playlist_create", user_id=user_id, limit=10, window_seconds=60)

    record = get_generated_playlist(db, generated_playlist_id=generated_playlist_id, user_id=user_id)
    if not record:
        raise HTTPException(status_code=404, detail="Generated playlist not found")

    sp = get_spotify_client(token)
    track_ids, resolved_now, resolution_rate_limited = _resolve_playlist_track_ids(db, sp, record, user_id)
    max_tracks = len(record.tracks)

    if len(track_ids) < max_tracks:
        fallback_ids = _fallback_top_listened_ids(db, user_id, limit=50)
        track_ids = _dedupe_keep_order(track_ids + fallback_ids)

    track_ids = track_ids[:max_tracks]
    playlist = _create_playlist_with_refresh(db, sp, user_id, record.name.replace("Preview", "Playlist"), track_ids)
    record = mark_generated_playlist_created(db, record=record, spotify_playlist_id=playlist.get("id"))

    warnings = _build_playlist_warnings(record.tracks, max_tracks, created_track_count=len(track_ids), spotify_rate_limited=resolution_rate_limited)

    return {
        "message": "Playlist generated",
        "playlist": playlist,
        "generated_playlist": serialize_generated_playlist(record, include_tracks=True),
        "tracks_added": len(track_ids),
        "resolved_spotify_ids_now": resolved_now,
        "warnings": warnings,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
    }


@router.post("/generated/{generated_playlist_id}/regenerate")
def regenerate_preview(generated_playlist_id: int, request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    record = get_generated_playlist(db, generated_playlist_id=generated_playlist_id, user_id=user_id)
    if not record:
        raise HTTPException(status_code=404, detail="Generated playlist not found")

    params = record.request_params_json
    try:
        request_params = json.loads(params or "{}")
    except Exception:
        request_params = {}

    payload = PlaylistGeneratePayload(
        min_known_ratio=float(request_params.get("min_known_ratio") or 0.6),
        diversity=float(request_params.get("diversity") or 0.5),
        familiarity=float(request_params.get("familiarity") or 0.5),
        max_tracks=int(request_params.get("max_tracks") or len(record.tracks) or 30),
        name=record.name.replace("Preview", "Regenerated Preview"),
        context_type=record.context_type,
    )
    return _build_preview(db, user_id, payload)


@router.post("/generate")
def generate(payload: PlaylistGeneratePayload, request: Request, db: Session = Depends(get_db)):
    started = time.perf_counter()
    logger.info(
        "playlist.generate.start max_tracks=%s diversity=%s familiarity=%s min_known_ratio=%s",
        payload.max_tracks,
        payload.diversity,
        payload.familiarity,
        payload.min_known_ratio,
    )

    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    token = session.get("token")
    if not token or not user_id:
        logger.info("playlist.generate.unauthorized")
        raise HTTPException(status_code=401, detail="User not logged in")

    preview_response = _build_preview(db, user_id, payload)
    generated_playlist = preview_response["generated_playlist"]
    preview_id = generated_playlist["id"]
    logger.info(
        "playlist.generate.preview_done generated_playlist_id=%s candidates=%s",
        preview_id,
        preview_response["recommendation_candidates"],
    )

    sp = get_spotify_client(token)
    record = get_generated_playlist(db, generated_playlist_id=preview_id, user_id=user_id)
    track_ids, resolved_now, resolution_rate_limited = _resolve_playlist_track_ids(db, sp, record, user_id)

    max_tracks = payload.max_tracks
    if len(track_ids) < max_tracks:
        fallback_ids = _fallback_top_listened_ids(db, user_id, limit=50)
        track_ids = _dedupe_keep_order(track_ids + fallback_ids)
    track_ids = track_ids[:max_tracks]

    playlist = _create_playlist_with_refresh(db, sp, user_id, record.name.replace("Preview", "Playlist"), track_ids)
    record = mark_generated_playlist_created(db, record=record, spotify_playlist_id=playlist.get("id"))
    warnings = _build_playlist_warnings(record.tracks, max_tracks, created_track_count=len(track_ids), spotify_rate_limited=resolution_rate_limited)

    explain = []
    for track in sorted(record.tracks, key=lambda item: item.position)[:10]:
        try:
            components = json.loads(track.score_breakdown_json or "{}")
        except Exception:
            components = {}
        try:
            explanation = json.loads(track.explanation_json or "{}")
        except Exception:
            explanation = {}
        explain.append(
            {
                "title": track.song.title if track.song else None,
                "artist": track.song.artist.name if track.song and track.song.artist else None,
                "score": round(float(track.final_score or 0), 4),
                "components": components,
                "spotify_id": track.song.spotify_id if track.song else None,
                "enrichment_status": track.song.enrichment_status if track.song else None,
                "explanation": explanation,
            }
        )

    elapsed = round(time.perf_counter() - started, 2)
    logger.info("playlist.generate.done seconds=%.2f warnings=%s", elapsed, len(warnings))
    known_track_ratio = (
        sum(1 for track in record.tracks if track.song and track.song.spotify_id) / max(1, len(record.tracks))
    )
    return {
        "message": "Playlist generated",
        "playlist": playlist,
        "generated_playlist_id": record.id,
        "generated_playlist": serialize_generated_playlist(record, include_tracks=True),
        "tracks_added": len(track_ids),
        "resolved_spotify_ids_now": resolved_now,
        "recommendation_candidates": preview_response["recommendation_candidates"],
        "known_track_ratio": round(known_track_ratio, 3),
        "warnings": warnings,
        "elapsed_seconds": elapsed,
        "quality_controls": preview_response["quality_controls"],
        "explanations": explain,
    }


@router.post("/context/{context_name}")
def generate_context_playlist(context_name: str, request: Request, db: Session = Depends(get_db)):
    key = context_name.lower().strip()
    if key not in CONTEXT_DEFAULTS:
        raise HTTPException(status_code=404, detail="Unknown context. Use one of: focus, workout, late-night, chill")

    defaults = CONTEXT_DEFAULTS[key]
    payload = PlaylistGeneratePayload(
        context_type=key,
        diversity=defaults["diversity"],
        familiarity=defaults["familiarity"],
        max_tracks=defaults["max_tracks"],
        min_known_ratio=0.65 if key == "workout" else 0.55,
    )
    result = generate(payload, request, db)
    result["context"] = key
    result["current_hour_utc"] = utcnow().hour
    return result


# ── Scheduled playlist refresh ───────────────────────────────────────────────

def _run_schedule(db: Session, schedule):
    """Regenerate the playlist for one schedule using the existing pipeline and
    record the run. Returns the new generated playlist id (or None on failure)."""
    payload = PlaylistGeneratePayload(
        min_known_ratio=schedule.min_known_ratio,
        diversity=schedule.diversity,
        familiarity=schedule.familiarity,
        max_tracks=schedule.max_tracks,
        name=schedule.name,
        context_type=schedule.context_type,
    )
    generated_id = None
    try:
        preview = _build_preview(db, schedule.user_id, payload)
        generated_id = preview["generated_playlist"]["id"]
    except Exception:
        logger.exception("playlist.schedule.run_failed schedule_id=%s user_id=%s", schedule.id, schedule.user_id)
    # Always advance the clock so a persistently failing schedule doesn't run on
    # every single request — it retries next cadence instead.
    mark_ran(db, schedule=schedule, generated_playlist_id=generated_id)
    return generated_id


def _process_due_schedules(db: Session, user_id: str) -> int:
    ran = 0
    for schedule in due_schedules(db, user_id=user_id):
        _run_schedule(db, schedule)
        ran += 1
    return ran


@router.get("/schedules")
def get_schedules(request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    # Opportunistically run anything due before listing, so simply opening the
    # page keeps schedules fresh without an external cron.
    ran = _process_due_schedules(db, user_id)
    schedules = list_schedules(db, user_id=user_id)
    return {"items": [serialize_schedule(s) for s in schedules], "ran_now": ran}


@router.post("/schedules")
def post_schedule(payload: ScheduleCreatePayload, request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    if payload.cadence not in VALID_CADENCES:
        raise HTTPException(status_code=400, detail=f"Unknown cadence. Use one of: {', '.join(sorted(VALID_CADENCES))}")
    if count_schedules(db, user_id=user_id) >= MAX_SCHEDULES_PER_USER:
        raise HTTPException(status_code=400, detail=f"You can have at most {MAX_SCHEDULES_PER_USER} schedules.")

    schedule = create_schedule(
        db,
        user_id=user_id,
        cadence=payload.cadence,
        name=payload.name,
        context_type=payload.context_type,
        min_known_ratio=payload.min_known_ratio,
        diversity=payload.diversity,
        familiarity=payload.familiarity,
        max_tracks=payload.max_tracks,
    )
    return serialize_schedule(schedule)


@router.post("/schedules/{schedule_id}/run")
def run_schedule_now(schedule_id: int, request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    schedule = get_schedule(db, schedule_id=schedule_id, user_id=user_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    enforce_rate_limit(request, namespace="playlist_schedule_run", user_id=user_id, limit=10, window_seconds=60)
    generated_id = _run_schedule(db, schedule)
    return {"schedule": serialize_schedule(schedule), "generated_playlist_id": generated_id}


@router.delete("/schedules/{schedule_id}")
def remove_schedule(schedule_id: int, request: Request, db: Session = Depends(get_db)):
    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not logged in")

    if not delete_schedule(db, schedule_id=schedule_id, user_id=user_id):
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"message": "Schedule deleted", "schedule_id": schedule_id}
