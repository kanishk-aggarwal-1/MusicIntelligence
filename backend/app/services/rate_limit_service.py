import json
import logging
from datetime import timedelta
from time import time

from fastapi import HTTPException, Request
from sqlalchemy.exc import IntegrityError

from ..database import SessionLocal
from ..models.api_cache import ApiCache
from ..time_utils import utcnow_naive


logger = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    real_ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded and (real_ip in {"127.0.0.1", "::1"} or real_ip.startswith("10.")):
        # Only trust the header when the direct connection comes from a known proxy.
        return forwarded.split(",", 1)[0].strip()
    return real_ip


def enforce_rate_limit(
    request: Request,
    *,
    namespace: str,
    user_id: str | None = None,
    limit: int = 10,
    window_seconds: int = 60,
) -> None:
    key = f"rate_limit:{namespace}:{user_id or _client_ip(request)}"
    now = time()
    cutoff = now - window_seconds
    db = SessionLocal()

    try:
        now_dt = utcnow_naive()
        db.query(ApiCache).filter(
            ApiCache.provider == "rate_limit",
            ApiCache.expires_at < now_dt,
        ).delete(synchronize_session=False)

        row = (
            db.query(ApiCache)
            .filter(ApiCache.provider == "rate_limit", ApiCache.cache_key == key)
            .first()
        )

        timestamps = []
        if row and row.response_json:
            try:
                timestamps = [float(item) for item in json.loads(row.response_json)]
            except Exception:
                timestamps = []

        timestamps = [item for item in timestamps if item > cutoff]

        if len(timestamps) >= limit:
            retry_after = max(1, int(window_seconds - (now - timestamps[0])))
            db.commit()
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please wait a moment and try again.",
                headers={"Retry-After": str(retry_after)},
            )

        timestamps.append(now)
        serialized = json.dumps(timestamps)
        expires_at = now_dt + timedelta(seconds=window_seconds)

        if row:
            row.response_json = serialized
            row.status_code = 200
            row.error = None
            row.fetched_at = now_dt
            row.expires_at = expires_at
        else:
            db.add(
                ApiCache(
                    provider="rate_limit",
                    cache_key=key,
                    response_json=serialized,
                    status_code=200,
                    error=None,
                    fetched_at=now_dt,
                    expires_at=expires_at,
                )
            )
        db.commit()
    except HTTPException:
        raise
    except IntegrityError:
        db.rollback()
        logger.warning("rate_limit.write_conflict namespace=%s", namespace)
    except Exception:
        db.rollback()
        logger.warning("rate_limit.failed_open namespace=%s", namespace, exc_info=True)
    finally:
        db.close()
