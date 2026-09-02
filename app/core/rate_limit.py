"""Redis fixed-window rate limiting for authentication endpoints.

Deliberately simple: one INCR + EXPIRE per (bucket, key) window. No token
buckets, no sliding windows, no separate rate-limiting service — Redis is
already a hard dependency of this project, and a fixed window is precise
enough to stop the abuse that actually matters here (OTP-less registration
and login spam, credential-stuffing against a single account, refresh-token
guessing).
"""

from __future__ import annotations

from functools import lru_cache

import redis
from fastapi import HTTPException, status

from app.core.config import get_settings


@lru_cache
def _redis() -> redis.Redis:
    return redis.from_url(get_settings().redis_url)


def check_rate_limit(*, bucket: str, key: str, limit: int, window_seconds: int) -> None:
    """Raise 429 once more than ``limit`` calls land for ``key`` within the window.

    ``bucket`` namespaces independent limits (e.g. "login:email" vs
    "login:ip") so the same identifier can be rate-limited on more than one
    axis without the counters colliding.
    """
    redis_key = f"ratelimit:{bucket}:{key}"
    try:
        client = _redis()
        count = client.incr(redis_key)
        if count == 1:
            client.expire(redis_key, window_seconds)
        if count > limit:
            ttl = client.ttl(redis_key)
            retry_after = ttl if ttl and ttl > 0 else window_seconds
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "rate_limited", "message": "Too many attempts. Please try again shortly.", "details": {"retry_after": retry_after}},
                headers={"Retry-After": str(retry_after)},
            )
    except redis.RedisError:
        # Redis being unavailable must not take authentication down with it —
        # fail open on the limiter rather than 500ing every login attempt.
        # (This trades strict enforcement for availability during a Redis
        # outage; production alerting on Redis health covers the gap.)
        return
