from datetime import datetime

from fastapi import APIRouter

from ..services.metrics_service import get_metrics_snapshot

router = APIRouter(prefix="/ops", tags=["Operations"])


@router.get("/health")
def health():
    return {
        "status": "ok",
        "time_utc": datetime.utcnow().isoformat(),
    }


@router.get("/metrics")
def metrics():
    return get_metrics_snapshot()
