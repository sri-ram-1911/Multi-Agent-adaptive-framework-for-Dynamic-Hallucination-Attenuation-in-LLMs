"""In-memory corpus index — real embeddings + BM25, no database.

Lets the full pipeline run without Postgres/pgvector (demos, notebooks, unit
eval). Same ``retrieve()`` contract as ``HybridRetriever``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from app.core.logging import get_logger
from app.retrieval.embeddings import embed
from app.retrieval.reranker import rerank
from app.retrieval.schema import Evidence

log = get_logger("local_store")


def _chunk(text: str, size: int = 90) -> list[str]:
    words = text.split()
    return [" ".join(words[i : i + size]) for i in range(0, len(words), size)] or [text]


class LocalCorpus:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.meta: list[dict] = []
        self._emb: np.ndarray | None = None
        self._bm25: BM25Okapi | None = None

    @classmethod
    def from_dir(cls, path: str | Path) -> LocalCorpus:
        c = cls()
        files = sorted(Path(path).glob("*.json"))
        for f in files:
            doc = json.loads(f.read_text(encoding="utf-8"))
            for i, ch in enumerate(_chunk(doc["text"])):
                c.texts.append(ch)
                c.meta.append({
                    "chunk_id": f"{f.stem}-{i}",
                    "document_id": f.stem,
                    "document_title": doc["title"],
                    "source": doc.get("source", "doc"),
                    "authority": doc.get("authority", 0.6),
                    "published_at": doc.get("published_at"),
                })
        c._build()
        log.info("local_corpus.loaded", docs=len(files), chunks=len(c.texts))
        return c

    def _build(self) -> None:
        self._emb = np.asarray(embed(self.texts), dtype=np.float32)
        self._bm25 = BM25Okapi([t.lower().split() for t in self.texts])

    def _freshness(self, published: str | None) -> float:
        if not published:
            return 0.6
        try:
            age = (datetime.now(UTC) - datetime.fromisoformat(published).replace(tzinfo=UTC)).days
        except ValueError:
            return 0.6
        return max(0.1, min(1.0, 1.0 - age / (5 * 365)))

    def retrieve(self, query: str, *, k: int = 8, rerank_k: int = 5, do_rerank: bool = True,
                 **_: object) -> list[Evidence]:
        if not self.texts:
            return []
        qv = np.asarray(embed([query], is_query=True)[0], dtype=np.float32)
        cos = self._emb @ qv
        bm = np.asarray(self._bm25.get_scores(query.lower().split()))
        # reciprocal-rank fusion of the two orderings
        rank_cos = np.argsort(-cos)
        rank_bm = np.argsort(-bm)
        rrf = np.zeros(len(self.texts))
        for r, idx in enumerate(rank_cos):
            rrf[idx] += 1 / (60 + r + 1)
        for r, idx in enumerate(rank_bm):
            rrf[idx] += 1 / (60 + r + 1)
        top = np.argsort(-rrf)[: max(k, rerank_k * 3)]

        evs = [
            Evidence(
                chunk_id=self.meta[i]["chunk_id"],
                document_id=self.meta[i]["document_id"],
                document_title=self.meta[i]["document_title"],
                source=self.meta[i]["source"],
                text=self.texts[i],
                vector_score=float(cos[i]),
                keyword_score=float(bm[i]),
                fused_score=float(rrf[i]),
                authority=float(self.meta[i]["authority"]),
                freshness=self._freshness(self.meta[i]["published_at"]),
            )
            for i in top
        ]
        evs = rerank(query, evs, top_k=rerank_k) if do_rerank else evs[:rerank_k]
        for e in evs:
            rel = max(0.0, min(1.0, e.rerank_score if e.rerank_score else e.vector_score))
            e.source_score = round(0.4 * e.authority + 0.2 * e.freshness + 0.4 * rel, 3)
        return evs

    def retrieve_multi(self, queries: list[str], **kw) -> list[Evidence]:
        seen: dict[str, Evidence] = {}
        for q in queries:
            for e in self.retrieve(q, **kw):
                if e.chunk_id not in seen or e.rerank_score > seen[e.chunk_id].rerank_score:
                    seen[e.chunk_id] = e
        return sorted(seen.values(), key=lambda e: (e.rerank_score, e.fused_score), reverse=True)
