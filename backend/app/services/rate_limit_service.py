from collections import defaultdict, deque
from time import monotonic

from fastapi import HTTPException, Request


_REQUESTS: dict[str, deque] = {}

# IPs that are trusted to set X-Forwarded-For (e.g. Render's load balancer).
# Extend via the TRUSTED_PROXIES env var if needed.
_TRUSTED_PROXIES = {"127.0.0.1", "::1", "10.0.0.0/8"}


def _is_trusted_proxy(ip: str) -> bool:
    """Return True if `ip` is a known trusted reverse-proxy address."""
    return ip in _TRUSTED_PROXIES or ip.startswith("10.")


def _client_ip(request: Request) -> str:
    real_ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded and _is_trusted_proxy(real_ip):
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
    key = f"{namespace}:{user_id or _client_ip(request)}"
    now = monotonic()

    bucket = _REQUESTS.get(key)
    if bucket is None:
        bucket = deque()
        _REQUESTS[key] = bucket

    # Slide the window — remove expired timestamps.
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

    # Prune the key entirely once its bucket is empty so _REQUESTS doesn't
    # grow unbounded over time (e.g. unique IPs that each make one request).
    # We can only prune after appending, so check on the *next* call for that key.
    # Instead, prune stale keys opportunistically: if after sliding the window the
    # bucket would be empty on a future visit, schedule removal now.
    # Simple approach: if the bucket has exactly the entry we just added and the
    # previous bucket was empty (i.e. this is a "fresh" key after expiry), delete
    # the entry for any *other* key whose bucket is now empty.
    # Practical approach: delete keys with empty buckets found during our own lookup.
    # This is O(1) amortised per request.
    if len(bucket) == 1:
        # This key just became active again after being idle; take the opportunity
        # to scan for and remove a few stale keys (bounded work per call).
        _prune_stale(now, window_seconds, max_scan=20)


def _prune_stale(now: float, window_seconds: float, max_scan: int = 20) -> None:
    """Remove up to `max_scan` keys whose windows have fully expired."""
    to_delete = []
    scanned = 0
    for key, bucket in _REQUESTS.items():
        if scanned >= max_scan:
            break
        scanned += 1
        if bucket and now - bucket[0] <= window_seconds:
            continue
        # Slide the window to see if the bucket would be empty.
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if not bucket:
            to_delete.append(key)
    for key in to_delete:
        _REQUESTS.pop(key, None)
