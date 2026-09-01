"""Evidence cache (proposal §11 — reduce latency and cost for repeated requests).

Synchronous Redis client because retrieval runs inside the (threadpooled)
orchestration graph. Silently degrades to no-op if Redis is unavailable.
"""

from __future__ import annotations

import contextlib
import hashlib
import json

import redis

from app.config import settings
from app.core.logging import get_logger
from app.retrieval.schema import Evidence

log = get_logger("evidence_cache")
_TTL_S = 3600
_client: redis.Redis | None = None


def _r() -> redis.Redis | None:
    global _client
    if _client is None:
        try:
            _client = redis.Redis.from_url(settings.redis_url, decode_responses=True,
                                           socket_connect_timeout=1)
            _client.ping()
        except Exception as exc:  # pragma: no cover
            log.warning("evidence_cache.unavailable", error=str(exc))
            _client = None
    return _client


def _key(tenant_id: str, query: str, k: int) -> str:
    h = hashlib.sha256(f"{tenant_id}|{query}|{k}".encode()).hexdigest()
    return f"ev:{h}"


def get_cached(tenant_id: str, query: str, k: int) -> list[Evidence] | None:
    r = _r()
    if r is None:
        return None
    try:
        raw = r.get(_key(tenant_id, query, k))
    except Exception:  # pragma: no cover
        return None
    return [Evidence(**d) for d in json.loads(raw)] if raw else None


def set_cached(tenant_id: str, query: str, k: int, evidence: list[Evidence]) -> None:
    r = _r()
    if r is None:
        return
    with contextlib.suppress(Exception):  # pragma: no cover
        r.set(_key(tenant_id, query, k),
              json.dumps([e.model_dump() for e in evidence]), ex=_TTL_S)
