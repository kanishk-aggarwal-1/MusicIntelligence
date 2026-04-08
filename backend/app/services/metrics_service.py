from collections import defaultdict
from datetime import UTC, datetime

METRICS = {
    "external_calls": defaultdict(int),
    "external_failures": defaultdict(int),
    "jobs": defaultdict(int),
    "started_at": datetime.now(UTC).isoformat(),
}


def record_external_call(service_name: str, ok: bool):
    METRICS["external_calls"][service_name] += 1
    if not ok:
        METRICS["external_failures"][service_name] += 1


def record_job(status: str):
    METRICS["jobs"][status] += 1


def get_metrics_snapshot():
    return {
        "started_at": METRICS["started_at"],
        "external_calls": dict(METRICS["external_calls"]),
        "external_failures": dict(METRICS["external_failures"]),
        "jobs": dict(METRICS["jobs"]),
    }
