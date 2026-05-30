from collections import defaultdict, deque
from time import monotonic

from fastapi import HTTPException, Request


_REQUESTS = defaultdict(deque)


def _client_ip(request: Request):
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(
    request: Request,
    *,
    namespace: str,
    user_id: str | None = None,
    limit: int = 10,
    window_seconds: int = 60,
):
    key = f"{namespace}:{user_id or _client_ip(request)}"
    now = monotonic()
    bucket = _REQUESTS[key]

    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()

    if len(bucket) >= limit:
        retry_after = max(1, int(window_seconds - (now - bucket[0])))
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait a moment and try again.",
            headers={"Retry-After": str(retry_after)},
        )

    bucket.append(now)
