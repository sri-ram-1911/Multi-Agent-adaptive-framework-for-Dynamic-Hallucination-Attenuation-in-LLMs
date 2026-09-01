"""Redis token-bucket rate limiter (per API key)."""

from __future__ import annotations

import time

from app.core.errors import MAAHAFError
from app.db.cache import get_redis


class RateLimited(MAAHAFError):
    status_code = 429
    code = "rate_limited"


async def check_rate_limit(key: str, *, limit: int = 60, window_s: int = 60) -> None:
    r = get_redis()
    bucket = f"rl:{key}:{int(time.time() // window_s)}"
    count = await r.incr(bucket)
    if count == 1:
        await r.expire(bucket, window_s)
    if count > limit:
        raise RateLimited(f"rate limit {limit}/{window_s}s exceeded")
