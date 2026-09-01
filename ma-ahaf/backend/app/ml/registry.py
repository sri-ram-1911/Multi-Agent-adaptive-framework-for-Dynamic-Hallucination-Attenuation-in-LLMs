"""Load trained artifacts with graceful fallbacks (rule-based) if not yet trained."""

from __future__ import annotations

import os
import threading

import joblib

from app.config import settings
from app.core.logging import get_logger

log = get_logger("ml.registry")
_lock = threading.Lock()
_cache: dict[str, object] = {}


def _path(name: str) -> str:
    return os.path.join(settings.artifacts_dir, name)


def load(name: str) -> object | None:
    if name in _cache:
        return _cache[name]
    with _lock:
        if name not in _cache:
            p = _path(name)
            if os.path.exists(p):
                try:
                    _cache[name] = joblib.load(p)
                    log.info("ml.artifact_loaded", name=name)
                except Exception as exc:  # pragma: no cover
                    log.warning("ml.artifact_load_failed", name=name, error=str(exc))
                    _cache[name] = None
            else:
                log.info("ml.artifact_missing_fallback", name=name)
                _cache[name] = None
    return _cache[name]


def clear() -> None:
    _cache.clear()
