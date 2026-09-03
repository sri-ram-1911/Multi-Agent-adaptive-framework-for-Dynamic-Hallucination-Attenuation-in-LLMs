"""Redis token-bucket rate limiter (per API key).

Fails **open** with a warning + metric if Redis is unreachable, so a cache outage
degrades protection rather than taking the whole API down. Flip `_FAIL_OPEN` to
False to fail closed in high-security deployments.
"""

from __future__ import annotations

import time

from prometheus_client import Counter

from app.core.errors import MAAHAFError
from app.core.logging import get_logger
from app.db.cache import get_redis

log = get_logger("ratelimit")
_FAIL_OPEN = True

RL_HITS = Counter("maahaf_rate_limited_total", "Requests rejected by the rate limiter")
RL_ERRORS = Counter("maahaf_rate_limiter_errors_total", "Rate limiter backend failures")


class RateLimited(MAAHAFError):
    status_code = 429
    code = "rate_limited"


async def check_rate_limit(key: str, *, limit: int = 60, window_s: int = 60) -> None:
    try:
        r = get_redis()
        bucket = f"rl:{key}:{int(time.time() // window_s)}"
        count = await r.incr(bucket)
        if count == 1:
            await r.expire(bucket, window_s)
    except Exception as exc:  # pragma: no cover - backend outage path
        RL_ERRORS.inc()
        log.warning("ratelimit.backend_unavailable", error=str(exc), fail_open=_FAIL_OPEN)
        if _FAIL_OPEN:
            return
        raise RateLimited("rate limiter unavailable") from exc

    if count > limit:
        RL_HITS.inc()
        raise RateLimited(f"rate limit {limit}/{window_s}s exceeded")
