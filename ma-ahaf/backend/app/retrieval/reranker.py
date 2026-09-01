"""Cross-encoder reranker (DL). Offline fallback = lexical overlap heuristic."""

from __future__ import annotations

import threading

from app.config import settings
from app.core.logging import get_logger
from app.retrieval.schema import Evidence

log = get_logger("reranker")
_lock = threading.Lock()
_model = None
_offline = settings.llm.provider == "mock"


def _load():
    global _model
    if _model is not None or _offline:
        return _model
    with _lock:
        if _model is None:
            from sentence_transformers import CrossEncoder

            log.info("reranker.loading", model=settings.reranker_model)
            _model = CrossEncoder(settings.reranker_model)
    return _model


def _overlap(q: str, t: str) -> float:
    qs, ts = set(q.lower().split()), set(t.lower().split())
    return len(qs & ts) / (len(qs) or 1)


def rerank(query: str, evidence: list[Evidence], *, top_k: int) -> list[Evidence]:
    if not evidence:
        return []
    if _offline:
        for e in evidence:
            e.rerank_score = _overlap(query, e.text)
    else:
        model = _load()
        scores = model.predict([(query, e.text) for e in evidence])
        for e, s in zip(evidence, scores, strict=True):
            e.rerank_score = float(s)
    ranked = sorted(evidence, key=lambda e: e.rerank_score, reverse=True)
    return ranked[:top_k]
