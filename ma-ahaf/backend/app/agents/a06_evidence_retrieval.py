"""Agent 6 — Evidence Retrieval Agent (proposal §7, §11).

For each non-creative claim: expand the query (if ambiguous), run hybrid
retrieval, and — for high-criticality / high-risk claims — also fetch
contradictory evidence. Evidence is cached in Redis.
"""

from __future__ import annotations

from app.agents.base import Agent
from app.config import settings
from app.orchestration.state import RequestState
from app.retrieval.cache import get_cached, set_cached
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.query_expansion import expand


class EvidenceRetrieval(Agent):
    name = "evidence_retrieval"
    number = 6

    def _run(self, state: RequestState):
        pv = state.policy
        retriever = HybridRetriever(state.db)
        want_expansion = state.ambiguity > 0.45 or pv.grounding_intensity > 0.7
        k = int(settings.retrieval_k * (0.6 + pv.grounding_intensity))
        rerank_k = settings.rerank_k + (2 if pv.grounding_intensity > 0.7 else 0)

        pooled: dict[str, object] = {}
        checked = 0
        for claim in state.claim_graph.claims:
            if claim.claim_type in ("creative", "opinion"):
                continue
            checked += 1
            queries = expand(state.gateway, claim.text, enabled=want_expansion)
            evs = _cached_retrieve(state, retriever, queries, k=k, rerank_k=rerank_k,
                                   grounding=pv.grounding_intensity)
            claim.evidence_ids = [e.chunk_id for e in evs[:rerank_k]]
            for e in evs:
                if e.chunk_id not in pooled or e.rerank_score > pooled[e.chunk_id].rerank_score:  # type: ignore[union-attr]
                    pooled[e.chunk_id] = e

        state.evidence = sorted(
            pooled.values(), key=lambda e: (e.rerank_score, e.fused_score), reverse=True  # type: ignore[union-attr]
        )
        coverage = _coverage(state)
        state.signals.evidence_coverage = coverage
        return (
            {"claims_checked": checked, "evidence_count": len(state.evidence),
             "coverage": round(coverage, 3), "query_expansion": want_expansion,
             "top_docs": list({e.document_title for e in state.evidence[:6]})},  # type: ignore[union-attr]
            f"retrieved {len(state.evidence)} unique passages; coverage={coverage:.2f}",
            settings.embedding_model,
        )


def _cached_retrieve(state, retriever, queries, *, k, rerank_k, grounding):
    key_q = " || ".join(queries)
    cached = get_cached(state.tenant_id, key_q, rerank_k)
    if cached:
        return cached
    evs = retriever.retrieve_multi(
        queries, tenant_id=state.tenant_id, k=k, rerank_k=rerank_k,
        grounding_intensity=grounding,
    )
    set_cached(state.tenant_id, key_q, rerank_k, evs)
    return evs


def _coverage(state: RequestState) -> float:
    checkable = [c for c in state.claim_graph.claims if c.claim_type not in ("creative", "opinion")]
    if not checkable:
        return 1.0
    with_ev = sum(1 for c in checkable if c.evidence_ids)
    return with_ev / len(checkable)
