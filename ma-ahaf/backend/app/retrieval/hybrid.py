"""Hybrid retriever: vector + BM25/FTS fused by Reciprocal Rank Fusion, then
MMR diversification, then optional cross-encoder rerank (proposal §11).
"""

from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from app.config import settings
from app.retrieval.embeddings import embed
from app.retrieval.keyword import keyword_search
from app.retrieval.reranker import rerank
from app.retrieval.schema import Evidence
from app.retrieval.vector_store import vector_search

_RRF_K = 60


def _rrf(rankings: list[list[Evidence]]) -> dict[str, Evidence]:
    fused: dict[str, Evidence] = {}
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, ev in enumerate(ranking):
            scores[ev.chunk_id] = scores.get(ev.chunk_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
            cur = fused.get(ev.chunk_id)
            if cur is None:
                fused[ev.chunk_id] = ev
            else:
                cur.vector_score = max(cur.vector_score, ev.vector_score)
                cur.keyword_score = max(cur.keyword_score, ev.keyword_score)
    for cid, ev in fused.items():
        ev.fused_score = scores[cid]
    return fused


def _mmr(query_vec: np.ndarray, cands: list[Evidence], *, k: int, lam: float = 0.7) -> list[Evidence]:
    if len(cands) <= k:
        return cands
    vecs = np.asarray(embed([c.text for c in cands]), dtype=np.float32)
    qsim = vecs @ query_vec
    selected: list[int] = []
    remaining = list(range(len(cands)))
    while len(selected) < k and remaining:
        best, best_val = None, -1e9
        for i in remaining:
            div = max((float(vecs[i] @ vecs[j]) for j in selected), default=0.0)
            val = lam * float(qsim[i]) - (1 - lam) * div
            if val > best_val:
                best, best_val = i, val
        selected.append(best)  # type: ignore[arg-type]
        remaining.remove(best)  # type: ignore[arg-type]
    return [cands[i] for i in selected]


class HybridRetriever:
    """`retrieve()` is the single entry point used by agents."""

    def __init__(self, db: Session):
        self.db = db

    def retrieve(
        self,
        query: str,
        *,
        tenant_id: str,
        k: int | None = None,
        rerank_k: int | None = None,
        grounding_intensity: float = 0.6,
        do_rerank: bool = True,
    ) -> list[Evidence]:
        pool = int((k or settings.retrieval_k) * (1 + grounding_intensity))
        vec = vector_search(self.db, query, tenant_id=tenant_id, k=pool)
        kw = keyword_search(self.db, query, tenant_id=tenant_id, k=pool)
        fused = list(_rrf([vec, kw]).values())
        fused.sort(key=lambda e: e.fused_score, reverse=True)

        top_n = rerank_k or settings.rerank_k
        if not fused:
            return []
        qv = np.asarray(embed([query])[0], dtype=np.float32)
        diversified = _mmr(qv, fused[: max(top_n * 3, 12)], k=max(top_n * 2, 8))
        if do_rerank:
            return rerank(query, diversified, top_k=top_n)
        return diversified[:top_n]

    def retrieve_multi(self, queries: list[str], **kw) -> list[Evidence]:
        seen: dict[str, Evidence] = {}
        for q in queries:
            for e in self.retrieve(q, **kw):
                if e.chunk_id not in seen or e.rerank_score > seen[e.chunk_id].rerank_score:
                    seen[e.chunk_id] = e
        return sorted(seen.values(), key=lambda e: (e.rerank_score, e.fused_score), reverse=True)
