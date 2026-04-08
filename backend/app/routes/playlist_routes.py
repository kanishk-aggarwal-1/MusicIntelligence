import logging
import time
from datetime import datetime
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.listening_history import ListeningHistory
from ..models.song import Song
from ..services.recommendation_service import recommend_songs
from ..services.spotify_service import (
    create_playlist,
    get_spotify_client,
    load_request_user_session,
    load_user_session,
    resolve_track_id,
)

router = APIRouter(prefix="/playlists", tags=["Playlists"])
logger = logging.getLogger(__name__)


class PlaylistGeneratePayload(BaseModel):
    min_known_ratio: float = 0.6
    diversity: float = 0.5
    familiarity: float = 0.5
    max_tracks: int = 30


def _dedupe_keep_order(values):
    seen = set()
    out = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _resolve_recommended_track_ids(db, sp, details, user_id: str):
    resolved_now = 0
    track_ids = []
    rate_limited = False

    for item in details:
        song = item["song"]
        track_id = song.spotify_id

        if not track_id:
            artist_name = song.artist.name if song.artist else None
            try:
                track_id = resolve_track_id(sp, song.title, artist_name)
            except Exception as exc:
                status = getattr(exc, "http_status", None)
                if status == 401:
                    print(f"playlist.resolve.token_expired title={song.title} artist={artist_name}")
                    session = load_user_session(db, user_id=user_id)
                    refreshed_token = session.get("token")
                    if not refreshed_token:
                        raise
                    sp = get_spotify_client(refreshed_token)
                    track_id = resolve_track_id(sp, song.title, artist_name)
                elif status == 429:
                    print(f"playlist.resolve.rate_limited title={song.title} artist={artist_name}")
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

    return _dedupe_keep_order(track_ids), resolved_now, rate_limited


def _create_playlist_with_refresh(db, sp, user_id: str, track_ids):
    try:
        return create_playlist(sp, user_id, track_ids)
    except Exception as exc:
        if getattr(exc, "http_status", None) != 401:
            raise
        print(f"playlist.create.token_expired user_id={user_id}")
        session = load_user_session(db, user_id=user_id)
        refreshed_token = session.get("token")
        if not refreshed_token:
            raise
        refreshed_sp = get_spotify_client(refreshed_token)
        return create_playlist(refreshed_sp, user_id, track_ids)


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
            src = item["song"].discovery_source or "unknown"
            grouped.setdefault(src, []).append(item)

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
    unknown = [item for item in details if not item["song"].spotify_id]

    if len(known) < desired_known:
        return details

    reordered = known[:desired_known]
    for item in details:
        if item in reordered:
            continue
        reordered.append(item)
    return reordered


def _build_playlist_warnings(details, track_ids, max_tracks, discovery_summary, spotify_rate_limited=False):
    warnings = []
    seed_artists = int(discovery_summary.get("seed_artists") or 0)
    source_artists = int(discovery_summary.get("source_artists") or 0)
    if seed_artists and source_artists < seed_artists:
        warnings.append(f"Discovery found track sources for {source_artists} of {seed_artists} seed artists.")
    if not details:
        warnings.append("No recommendation candidates were produced from the current library.")
    if len(track_ids) < max_tracks:
        warnings.append(f"Only {len(track_ids)} Spotify-resolvable tracks were available for a target of {max_tracks}.")
    if len(track_ids) == 0:
        warnings.append("Playlist was created with no tracks because no Spotify-resolvable recommendations were found.")
    if spotify_rate_limited or discovery_summary.get("store_rate_limited"):
        warnings.append("Spotify search rate limit was hit during this request, so track resolution was cut short.")
    return warnings


@router.post("/generate")
def generate(payload: PlaylistGeneratePayload, request: Request, db: Session = Depends(get_db)):

    started = time.perf_counter()
    print(f"playlist.generate.start max_tracks={payload.max_tracks} diversity={payload.diversity} familiarity={payload.familiarity} min_known_ratio={payload.min_known_ratio}")

    session = load_request_user_session(db, request)

    user_id = session.get("user_id")
    token = session.get("token")

    if not token or not user_id:
        print("playlist.generate.unauthorized")
        raise HTTPException(status_code=401, detail="User not logged in")

    sp = get_spotify_client(token)

    t0 = time.perf_counter()
    requested_tracks = max(1, min(payload.max_tracks, 100))
    discovery_seed_limit = max(3, min(requested_tracks * 2, 30))
    discovery_store_limit = max(10, min(requested_tracks * 5, 50))
    print(f"playlist.generate.discovery_seed_limit={discovery_seed_limit} discovery_store_limit={discovery_store_limit}")
    recommendation_result = recommend_songs(
        db,
        user_id,
        return_details=True,
        min_known_ratio=payload.min_known_ratio,
        include_discovery_summary=True,
        allow_discovery=False,
        discovery_seed_limit=discovery_seed_limit,
        discovery_store_limit=discovery_store_limit,
    )
    print(f"playlist.generate.recommendations_done seconds={time.perf_counter() - t0:.2f}")

    details = recommendation_result["items"]
    discovery_summary = recommendation_result.get("discovery_summary") or {}
    print(f"playlist.generate.discovery_summary {discovery_summary}")

    details = _apply_quality_controls(details, payload.diversity, payload.familiarity)
    details = _enforce_known_ratio(details, requested_tracks, payload.min_known_ratio)
    print(f"playlist.generate.quality_controls_done candidates={len(details)}")

    t1 = time.perf_counter()
    track_ids, resolved_now, resolution_rate_limited = _resolve_recommended_track_ids(db, sp, details, user_id)
    print(f"playlist.generate.resolve_done seconds={time.perf_counter() - t1:.2f} resolved_now={resolved_now} track_ids={len(track_ids)} rate_limited={resolution_rate_limited}")

    if len(track_ids) < 10:
        t2 = time.perf_counter()
        fallback_ids = _fallback_top_listened_ids(db, user_id, limit=50)
        track_ids = _dedupe_keep_order(track_ids + fallback_ids)
        print(f"playlist.generate.fallback_done seconds={time.perf_counter() - t2:.2f} fallback_ids={len(fallback_ids)} total_track_ids={len(track_ids)}")

    max_tracks = max(1, min(payload.max_tracks, 100))
    track_ids = track_ids[:max_tracks]
    print(f"playlist.generate.trimmed target={max_tracks} final_track_ids={len(track_ids)}")

    t3 = time.perf_counter()
    playlist = _create_playlist_with_refresh(db, sp, user_id, track_ids)
    print(f"playlist.generate.spotify_create_done seconds={time.perf_counter() - t3:.2f} playlist_id={playlist.get('id')}")

    explain = [
        {
            "title": item["song"].title,
            "artist": item["song"].artist.name if item["song"].artist else None,
            "score": round(item["score"], 4),
            "reasons": item["reasons"],
            "components": item.get("components", {}),
            "spotify_id": item["song"].spotify_id,
            "discovery_source": item["song"].discovery_source,
            "discovery_confidence": item["song"].discovery_confidence,
            "enrichment_status": item["song"].enrichment_status,
        }
        for item in details[:10]
    ]

    known_ratio = (sum(1 for i in details[:30] if i["song"].spotify_id) / max(1, min(30, len(details)))) if details else 0
    warnings = _build_playlist_warnings(details, track_ids, max_tracks, discovery_summary, spotify_rate_limited=resolution_rate_limited)
    elapsed = round(time.perf_counter() - started, 2)
    print(f"playlist.generate.done seconds={elapsed:.2f} warnings={len(warnings)}")

    return {
        "message": "Playlist generated",
        "playlist": playlist,
        "tracks_added": len(track_ids),
        "resolved_spotify_ids_now": resolved_now,
        "recommendation_candidates": len(details),
        "known_track_ratio": round(known_ratio, 3),
        "discovery_summary": discovery_summary,
        "warnings": warnings,
        "elapsed_seconds": elapsed,
        "quality_controls": {
            "min_known_ratio": payload.min_known_ratio,
            "diversity": payload.diversity,
            "familiarity": payload.familiarity,
            "max_tracks": max_tracks,
        },
        "explanations": explain,
    }


@router.post("/context/{context_name}")
def generate_context_playlist(context_name: str, request: Request, db: Session = Depends(get_db)):
    started = time.perf_counter()
    print(f"playlist.context.start context={context_name}")

    session = load_request_user_session(db, request)
    user_id = session.get("user_id")
    token = session.get("token")

    if not token or not user_id:
        print(f"playlist.context.unauthorized context={context_name}")
        raise HTTPException(status_code=401, detail="User not logged in")

    sp = get_spotify_client(token)

    context_map = {
        "focus": {"hours": (9, 17), "genres": ["ambient", "instrumental", "classical", "lofi"]},
        "workout": {"hours": (6, 22), "genres": ["hip hop", "edm", "dance", "rock"]},
        "late-night": {"hours": (21, 4), "genres": ["chill", "rnb", "soul", "indie"]},
        "chill": {"hours": (0, 23), "genres": ["chill", "indie", "acoustic", "ambient"]},
    }

    key = context_name.lower().strip()
    cfg = context_map.get(key)
    if not cfg:
        raise HTTPException(status_code=404, detail="Unknown context. Use one of: focus, workout, late-night, chill")

    now_hour = datetime.utcnow().hour
    t0 = time.perf_counter()
    recommendation_result = recommend_songs(db, user_id, return_details=True, include_discovery_summary=True, allow_discovery=False, discovery_seed_limit=12, discovery_store_limit=30)
    print(f"playlist.context.recommendations_done context={key} seconds={time.perf_counter() - t0:.2f}")
    details = recommendation_result["items"]
    discovery_summary = recommendation_result.get("discovery_summary") or {}

    filtered = []
    for item in details:
        song = item["song"]
        genre = (song.genre or "").lower()

        if cfg["genres"] and not any(g in genre for g in cfg["genres"]):
            continue

        filtered.append(item)

    if not filtered:
        filtered = details

    t1 = time.perf_counter()
    track_ids, resolved_now, resolution_rate_limited = _resolve_recommended_track_ids(db, sp, filtered, user_id)
    print(f"playlist.context.resolve_done context={key} seconds={time.perf_counter() - t1:.2f} resolved_now={resolved_now} track_ids={len(track_ids)} rate_limited={resolution_rate_limited}")

    if len(track_ids) < 10:
        t2 = time.perf_counter()
        fallback_ids = _fallback_top_listened_ids(db, user_id, limit=50)
        track_ids = _dedupe_keep_order(track_ids + fallback_ids)
        print(f"playlist.context.fallback_done context={key} seconds={time.perf_counter() - t2:.2f} fallback_ids={len(fallback_ids)} total_track_ids={len(track_ids)}")

    track_ids = track_ids[:30]

    t3 = time.perf_counter()
    playlist = _create_playlist_with_refresh(db, sp, user_id, track_ids)
    print(f"playlist.context.spotify_create_done context={key} seconds={time.perf_counter() - t3:.2f} playlist_id={playlist.get('id')}")

    warnings = _build_playlist_warnings(filtered, track_ids, 30, discovery_summary, spotify_rate_limited=resolution_rate_limited)
    elapsed = round(time.perf_counter() - started, 2)
    print(f"playlist.context.done context={key} seconds={elapsed:.2f} warnings={len(warnings)}")

    return {
        "message": "Context playlist generated",
        "context": key,
        "current_hour_utc": now_hour,
        "tracks_added": len(track_ids),
        "resolved_spotify_ids_now": resolved_now,
        "discovery_summary": discovery_summary,
        "warnings": warnings,
        "elapsed_seconds": elapsed,
        "playlist": playlist,
    }




