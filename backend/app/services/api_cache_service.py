import json
from datetime import timedelta

from sqlalchemy.exc import IntegrityError

from ..database import SessionLocal
from ..models.api_cache import ApiCache
from ..time_utils import parse_utc_datetime, utcnow_naive


SUCCESS_TTL = timedelta(days=7)
FAILURE_TTL = timedelta(hours=6)


def get_cached_response(provider: str, cache_key: str):
    db = SessionLocal()
    try:
        row = (
            db.query(ApiCache)
            .filter(ApiCache.provider == provider, ApiCache.cache_key == cache_key)
            .first()
        )
        if not row:
            return None
        now = utcnow_naive()
        if row.expires_at and row.expires_at <= now:
            return None
        payload = json.loads(row.response_json) if row.response_json else None
        return {
            "payload": payload,
            "status_code": row.status_code,
            "error": row.error,
            "fetched_at": row.fetched_at,
            "expires_at": row.expires_at,
        }
    finally:
        db.close()


def store_cached_response(provider: str, cache_key: str, payload=None, status_code: int | None = 200, error: str | None = None, ttl: timedelta | None = None):
    db = SessionLocal()
    try:
        now = utcnow_naive()
        expires_at = now + (ttl or (FAILURE_TTL if error else SUCCESS_TTL))
        row = (
            db.query(ApiCache)
            .filter(ApiCache.provider == provider, ApiCache.cache_key == cache_key)
            .first()
        )
        serialized = json.dumps(payload) if payload is not None else None
        if row:
            row.response_json = serialized
            row.status_code = status_code
            row.error = error
            row.fetched_at = now
            row.expires_at = expires_at
        else:
            row = ApiCache(
                provider=provider,
                cache_key=cache_key,
                response_json=serialized,
                status_code=status_code,
                error=error,
                fetched_at=now,
                expires_at=expires_at,
            )
            db.add(row)
        db.commit()
        return row
    except IntegrityError:
        db.rollback()
        return store_cached_response(provider, cache_key, payload=payload, status_code=status_code, error=error, ttl=ttl)
    finally:
        db.close()


def clear_provider_cache(provider: str):
    db = SessionLocal()
    try:
        deleted = db.query(ApiCache).filter(ApiCache.provider == provider).delete()
        db.commit()
        return deleted
    finally:
        db.close()
