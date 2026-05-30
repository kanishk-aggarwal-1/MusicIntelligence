from collections import defaultdict
from datetime import UTC, datetime

METRICS = {
    "external_calls": defaultdict(int),
    "external_failures": defaultdict(int),
    "jobs": defaultdict(int),
    "job_failures": defaultdict(int),
    "requests": defaultdict(int),
    "request_statuses": defaultdict(int),
    "timings": defaultdict(lambda: {"count": 0, "total_seconds": 0.0, "max_seconds": 0.0}),
    "started_at": datetime.now(UTC).isoformat(),
}


def record_external_call(service_name: str, ok: bool):
    METRICS["external_calls"][service_name] += 1
    if not ok:
        METRICS["external_failures"][service_name] += 1


def record_job(status: str, job_type: str | None = None):
    METRICS["jobs"][status] += 1
    if job_type:
        METRICS["jobs"][f"{job_type}.{status}"] += 1


def record_job_failure(job_type: str, error_type: str):
    METRICS["job_failures"][f"{job_type}.{error_type}"] += 1


def record_request(method: str, path: str, status_code: int, elapsed_seconds: float):
    # `path` should be the route *template* (e.g. "/songs/{song_id}"), not the
    # rendered path ("/songs/123"), to keep cardinality bounded.
    route_key = f"{method.upper()} {path}"
    METRICS["requests"][route_key] += 1
    METRICS["request_statuses"][str(status_code)] += 1
    record_timing(f"request.{route_key}", elapsed_seconds)


def record_timing(name: str, seconds: float):
    safe_seconds = max(0.0, float(seconds or 0.0))
    timing = METRICS["timings"][name]
    timing["count"] += 1
    timing["total_seconds"] += safe_seconds
    timing["max_seconds"] = max(timing["max_seconds"], safe_seconds)


def get_metrics_snapshot():
    timings = {}
    for name, timing in METRICS["timings"].items():
        count = int(timing["count"] or 0)
        total = float(timing["total_seconds"] or 0.0)
        timings[name] = {
            "count": count,
            "total_seconds": round(total, 4),
            "avg_seconds": round(total / count, 4) if count else 0.0,
            "max_seconds": round(float(timing["max_seconds"] or 0.0), 4),
        }

    return {
        "started_at": METRICS["started_at"],
        "external_calls": dict(METRICS["external_calls"]),
        "external_failures": dict(METRICS["external_failures"]),
        "jobs": dict(METRICS["jobs"]),
        "job_failures": dict(METRICS["job_failures"]),
        "requests": dict(METRICS["requests"]),
        "request_statuses": dict(METRICS["request_statuses"]),
        "timings": timings,
    }
