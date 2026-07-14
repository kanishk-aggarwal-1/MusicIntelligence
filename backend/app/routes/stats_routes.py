"""Public, read-only live metrics.

GET /stats   — JSON aggregates (powers the frontend Stats page).
GET /metrics — Prometheus exposition format (powers Grafana / scraping).

Both endpoints expose only non-sensitive cumulative aggregates — counts and
rates, never tokens or PII. Safe to expose publicly on the deployed app.
"""
import threading
import time

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from ..services import live_metrics_service
from ..services.live_metrics_service import CACHE_HITS, CACHE_MISSES, LASTFM_CALLS, PLAYLIST_TRACKS_REQUESTED, PLAYLIST_TRACKS_RESOLVED, PLAYLISTS_GENERATED, SPOTIFY_CALLS, TRACKS_ENRICHED, TRACKS_SYNCED

router = APIRouter(tags=["Stats"])

# Monitoring scrapes should not keep serverless Postgres awake continuously.
# Operational counters can safely be a few minutes behind live traffic.
METRICS_CACHE_TTL_SECONDS = 10 * 60
_metrics_cache: dict[int, tuple[float, dict]] = {}
_metrics_cache_lock = threading.Lock()


def _cached_counters() -> dict:
    key = id(live_metrics_service.engine)
    now = time.monotonic()
    cached = _metrics_cache.get(key)
    if cached and now - cached[0] < METRICS_CACHE_TTL_SECONDS:
        return cached[1]
    with _metrics_cache_lock:
        cached = _metrics_cache.get(key)
        if cached and now - cached[0] < METRICS_CACHE_TTL_SECONDS:
            return cached[1]
        counters = live_metrics_service.get_counters()
        _metrics_cache.clear()
        _metrics_cache[key] = (now, counters)
        return counters

_PROM_HELP = {
    CACHE_HITS:                "musicintel_cache_hits_total",
    CACHE_MISSES:              "musicintel_cache_misses_total",
    SPOTIFY_CALLS:             "musicintel_spotify_calls_total",
    LASTFM_CALLS:              "musicintel_lastfm_calls_total",
    TRACKS_SYNCED:             "musicintel_tracks_synced_total",
    TRACKS_ENRICHED:           "musicintel_tracks_enriched_total",
    PLAYLISTS_GENERATED:       "musicintel_playlists_generated_total",
    PLAYLIST_TRACKS_REQUESTED: "musicintel_playlist_tracks_requested_total",
    PLAYLIST_TRACKS_RESOLVED:  "musicintel_playlist_tracks_resolved_total",
}


@router.get("/stats")
def public_stats():
    return live_metrics_service.build_stats(_cached_counters())


@router.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics():
    """Prometheus text exposition format for scraping by Prometheus / Grafana."""
    counters = _cached_counters()
    lines = []
    for counter_name, prom_name in _PROM_HELP.items():
        lines.append(f"# HELP {prom_name} Cumulative count from live traffic")
        lines.append(f"# TYPE {prom_name} counter")
        lines.append(f"{prom_name} {counters.get(counter_name, 0)}")

    # Derived gauges (rates computed from counters).
    hits = counters.get(CACHE_HITS, 0)
    total = hits + counters.get(CACHE_MISSES, 0)
    hit_rate = round((hits / total) * 100, 1) if total else 0.0
    requested = counters.get(PLAYLIST_TRACKS_REQUESTED, 0)
    resolved = counters.get(PLAYLIST_TRACKS_RESOLVED, 0)
    res_rate = round((resolved / requested) * 100, 1) if requested else 0.0

    lines += [
        "# HELP musicintel_cache_hit_rate_pct Cache hit rate percentage",
        "# TYPE musicintel_cache_hit_rate_pct gauge",
        f"musicintel_cache_hit_rate_pct {hit_rate}",
        "# HELP musicintel_playlist_resolution_rate_pct Playlist track resolution rate percentage",
        "# TYPE musicintel_playlist_resolution_rate_pct gauge",
        f"musicintel_playlist_resolution_rate_pct {res_rate}",
    ]
    return "\n".join(lines) + "\n"
