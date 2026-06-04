"""Public, read-only live metrics.

GET /stats exposes only non-sensitive cumulative aggregates (counts and rates)
backed by the persistent Postgres counters — no tokens, no PII, no per-user data.
Safe to show publicly on the deployed app.
"""
from fastapi import APIRouter

from ..services.live_metrics_service import build_stats

router = APIRouter(tags=["Stats"])


@router.get("/stats")
def public_stats():
    return build_stats()
