import requests
import time

from ..config import settings
from .metrics_service import record_external_call


CACHE = {}
CACHE_TTL = 3600


def lastfm_request(method: str, params=None):

    if params is None:
        params = {}

    params.update(
        {
            "method": method,
            "api_key": settings.LASTFM_API_KEY,
            "format": "json"
        }
    )

    cache_key = f"{method}:{str(sorted(params.items()))}"
    now = time.time()

    if cache_key in CACHE:
        data, timestamp = CACHE[cache_key]

        if now - timestamp < CACHE_TTL:
            return data

    time.sleep(0.2)

    try:
        response = requests.get(
            settings.LASTFM_API_URL,
            params=params,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        CACHE[cache_key] = (data, now)
        record_external_call("lastfm", ok=True)
        return data
    except Exception:
        record_external_call("lastfm", ok=False)
        raise


def get_similar_tracks(artist: str, track: str):

    return lastfm_request(
        "track.getSimilar",
        {
            "artist": artist,
            "track": track
        }
    )


def get_similar_artists(artist):

    data = lastfm_request(
        "artist.getsimilar",
        {
            "artist": artist,
            "limit": 10
        }
    )

    return data.get("similarartists", {}).get("artist", [])


def get_artist_top_tracks(artist: str, limit: int = 5):

    data = lastfm_request(
        "artist.gettoptracks",
        {
            "artist": artist,
            "limit": max(1, min(int(limit), 25)),
            "autocorrect": 1,
        }
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
            "autocorrect": 1
        }
    )


def get_track_info(artist: str, track: str):

    return lastfm_request(
        "track.getInfo",
        {
            "artist": artist,
            "track": track,
            "autocorrect": 1
        }
    )


def get_artist_tags(artist: str):

    return lastfm_request(
        "artist.getTopTags",
        {
            "artist": artist,
            "autocorrect": 1
        }
    )
