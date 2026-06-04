import json
import time

import requests

from ..config import settings
from . import live_metrics_service
from .api_cache_service import get_cached_response, store_cached_response
from .metrics_service import record_external_call


CACHE_TTL_SECONDS = 3600


def _make_cache_key(method: str, params: dict):
    return json.dumps({"method": method, "params": sorted(params.items())}, sort_keys=True)


def lastfm_request(method: str, params=None):
    if params is None:
        params = {}

    request_params = dict(params)
    request_params.update(
        {
            "method": method,
            "api_key": settings.LASTFM_API_KEY,
            "format": "json",
        }
    )

    cache_key = _make_cache_key(method, request_params)
    cached = get_cached_response("lastfm", cache_key)
    if cached is not None:
        # Cache hit — a real Last.fm call was avoided.
        live_metrics_service.increment(live_metrics_service.CACHE_HITS)
        if cached.get("error"):
            record_external_call("lastfm_cache", ok=False)
            raise RuntimeError(cached["error"])
        record_external_call("lastfm_cache", ok=True)
        return cached.get("payload") or {}

    # Cache miss — we are about to make a real external Last.fm request.
    live_metrics_service.increment_many({
        live_metrics_service.CACHE_MISSES: 1,
        live_metrics_service.LASTFM_CALLS: 1,
    })
    time.sleep(0.2)

    try:
        response = requests.get(
            settings.LASTFM_API_URL,
            params=request_params,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        store_cached_response("lastfm", cache_key, payload=data, status_code=response.status_code)
        record_external_call("lastfm", ok=True)
        return data
    except Exception as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        store_cached_response("lastfm", cache_key, payload=None, status_code=status_code, error=str(exc))
        record_external_call("lastfm", ok=False)
        raise


def get_similar_tracks(artist: str, track: str):
    return lastfm_request(
        "track.getSimilar",
        {
            "artist": artist,
            "track": track,
        },
    )


def get_similar_artists(artist):
    data = lastfm_request(
        "artist.getsimilar",
        {
            "artist": artist,
            "limit": 10,
        },
    )

    return data.get("similarartists", {}).get("artist", [])


def get_artist_top_tracks(artist: str, limit: int = 5):
    data = lastfm_request(
        "artist.gettoptracks",
        {
            "artist": artist,
            "limit": max(1, min(int(limit), 25)),
            "autocorrect": 1,
        },
    )

    tracks = data.get("toptracks", {}).get("track", [])
    if isinstance(tracks, dict):
        tracks = [tracks]

    out = []
    for t in tracks:
        name = (t.get("name") or "").strip()
        if not name:
            continue
        out.append({"title": name, "artist": artist})

    return out


def get_track_tags(artist: str, track: str):
    return lastfm_request(
        "track.getTopTags",
        {
            "artist": artist,
            "track": track,
            "autocorrect": 1,
        },
    )


def get_track_info(artist: str, track: str):
    return lastfm_request(
        "track.getInfo",
        {
            "artist": artist,
            "track": track,
            "autocorrect": 1,
        },
    )


def get_artist_tags(artist: str):
    return lastfm_request(
        "artist.getTopTags",
        {
            "artist": artist,
            "autocorrect": 1,
        },
    )
