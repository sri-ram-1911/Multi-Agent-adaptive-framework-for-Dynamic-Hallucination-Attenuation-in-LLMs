"""POST /v1/generate — the main adaptive hallucination-attenuation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.deps import Principal, requires
from app.api.schemas import ClaimOut, EvidenceOut, GenerateRequest, GenerateResponse, SegmentOut
from app.controller.risk_model import explain
from app.db.session import get_db
from app.orchestration.pipeline import run_pipeline

router = APIRouter(prefix="/v1", tags=["generate"])


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    body: GenerateRequest,
    principal: Principal = Depends(requires("operator")),
    db: Session = Depends(get_db),
) -> GenerateResponse:
    state = await run_in_threadpool(
        run_pipeline,
        db,
        tenant_id=principal.tenant_id,
        prompt=body.prompt,
        context=body.context,
        policy_profile=body.policy_profile,
        policy_overrides=body.policy_overrides,
    )
    cg = state.claim_graph
    usage = state.__dict__.get("_usage")
    return GenerateResponse(
        trace_id=state.request_id,
        response=state.final_response,
        segments=[SegmentOut(**s.model_dump()) for s in state.segments],
        action=state.action,
        action_reason=state.action_reason,
        confidence=state.confidence,
        calibrated_confidence=state.calibrated_confidence,
        consistency_gap=state.consistency_gap,
        task_type=state.task_type,
        risk_score=state.risk_score,
        max_claim_risk=round(cg.max_risk(), 4),
        agent_disagreement=state.agent_disagreement,
        creativity_score=state.creativity_score,
        policy_vector=state.policy.model_dump() if state.policy else {},
        claims=[
            ClaimOut(
                id=c.id, text=c.text, claim_type=c.claim_type, criticality=c.criticality,
                verdict=c.verdict, risk_score=c.risk_score, risk_level=c.risk_level,
                risk_contributions=c.risk_contributions, evidence_ids=c.evidence_ids,
                explanation=explain(c),
            )
            for c in cg.claims
        ],
        evidence=[
            EvidenceOut(
                chunk_id=e.chunk_id, document_title=e.document_title, source=e.source,
                text=e.text, source_score=e.source_score, rerank_score=round(e.rerank_score, 4),
                stance=e.stance,
            )
            for e in state.evidence
        ],
        usage={
            "tokens_in": getattr(usage, "tokens_in", 0),
            "tokens_out": getattr(usage, "tokens_out", 0),
            "cost_usd": round(getattr(usage, "cost_usd", 0.0), 6),
            "llm_calls": getattr(usage, "calls", 0),
        },
        latency_ms=state.__dict__.get("_latency_ms", 0),
    )
