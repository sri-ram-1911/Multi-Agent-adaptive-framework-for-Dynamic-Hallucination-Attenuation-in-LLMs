"""Agent 7 — Source Quality Agent (proposal §7).

Scores each retrieved passage on authority, freshness, relevance, consistency and
corroboration. ML: GradientBoosting regressor (`app.ml.train_source_quality`),
with an interpretable weighted fallback.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.agents.base import Agent
from app.db.models import Chunk, Document
from app.ml import registry
from app.ml.features import source_vector
from app.orchestration.state import RequestState

_FALLBACK_W = {"authority": 0.30, "freshness": 0.15, "relevance": 0.25,
               "consistency": 0.15, "corroboration": 0.15}


def _freshness(published_at) -> float:
    if not published_at:
        return 0.5
    age_days = (datetime.now(UTC) - published_at).days
    return max(0.1, min(1.0, 1.0 - age_days / (5 * 365)))


class SourceQuality(Agent):
    name = "source_quality"
    number = 7

    def _run(self, state: RequestState):
        if not state.evidence:
            return {"scored": 0}, "no evidence to score", "source-quality/v1"

        chunk_ids = [e.chunk_id for e in state.evidence]
        rows = state.db.execute(
            select(Chunk.id, Document.authority, Document.published_at, Document.source)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.id.in_(chunk_ids))
        ).all()
        meta = {r.id: r for r in rows}

        # corroboration = how many distinct documents cover similar ground
        doc_counts: dict[str, int] = {}
        for e in state.evidence:
            doc_counts[e.document_id] = doc_counts.get(e.document_id, 0) + 1
        distinct_docs = len(doc_counts)

        model_art = registry.load("source_quality.joblib")
        scores: list[float] = []
        for e in state.evidence:
            m = meta.get(e.chunk_id)
            authority = float(m.authority) if m else 0.5
            freshness = _freshness(m.published_at) if m else 0.5
            relevance = max(0.0, min(1.0, e.rerank_score if e.rerank_score else e.fused_score * 5))
            corroboration = min(1.0, distinct_docs / 4)

            feat = {"authority": authority, "freshness": freshness, "relevance": relevance,
                    "consistency": max(0.3, min(1.0, 0.5 + relevance / 2)),
                    "corroboration": corroboration}
            if model_art is not None:
                try:
                    q = float(model_art["model"].predict(source_vector(feat).reshape(1, -1))[0])
                except Exception:  # pragma: no cover
                    q = sum(_FALLBACK_W[k] * v for k, v in feat.items())
            else:
                q = sum(_FALLBACK_W[k] * v for k, v in feat.items())

            e.authority = round(authority, 3)
            e.freshness = round(freshness, 3)
            e.source_score = round(max(0.0, min(1.0, q)), 3)
            scores.append(e.source_score)

        agreement = 1.0 - (max(scores) - min(scores)) if len(scores) > 1 else scores[0]
        state.signals.source_agreement = round(max(0.0, agreement), 3)
        return (
            {"scored": len(scores), "mean_source_score": round(sum(scores) / len(scores), 3),
             "source_agreement": state.signals.source_agreement, "distinct_docs": distinct_docs},
            f"mean source quality {sum(scores) / len(scores):.2f}, agreement {agreement:.2f}",
            "gbr-source-quality" if model_art else "source-quality/rules-v1",
        )
