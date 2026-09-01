"""Observability: list requests + fetch full audit traces (proposal §4, §18)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, requires
from app.core.errors import NotFound
from app.db import models
from app.db.repositories import get_audit, get_request, list_requests
from app.db.session import get_db

router = APIRouter(prefix="/v1/traces", tags=["observability"])


@router.get("")
def list_traces(
    principal: Principal = Depends(requires("viewer")),
    db: Session = Depends(get_db),
    limit: int = Query(50, le=200),
    action: str | None = None,
) -> list[dict]:
    reqs = list_requests(db, principal.tenant_id, limit=limit, action=action)
    return [
        {
            "trace_id": r.id, "created_at": r.created_at.isoformat(), "prompt": r.prompt[:200],
            "task_type": r.task_type, "action": r.action, "risk_score": r.risk_score,
            "max_claim_risk": r.max_claim_risk, "agent_disagreement": r.agent_disagreement,
            "calibrated_confidence": r.calibrated_confidence, "latency_ms": r.latency_ms,
            "total_tokens": r.total_tokens, "cost_usd": r.cost_usd,
        }
        for r in reqs
    ]


@router.get("/{trace_id}")
def get_trace(
    trace_id: str,
    principal: Principal = Depends(requires("viewer")),
    db: Session = Depends(get_db),
) -> dict:
    req = get_request(db, principal.tenant_id, trace_id)
    if req is None:
        raise NotFound("trace not found")
    audit = get_audit(db, principal.tenant_id, trace_id)
    claims = db.scalars(
        select(models.Claim).where(models.Claim.request_id == trace_id).order_by(models.Claim.ordinal)
    ).all()
    runs = db.scalars(
        select(models.AgentRun).where(models.AgentRun.request_id == trace_id)
        .order_by(models.AgentRun.ordinal)
    ).all()
    return {
        "trace_id": req.id,
        "prompt": req.prompt,
        "task_type": req.task_type,
        "policy_vector": req.policy_vector,
        "action": req.action,
        "final_response": req.final_response,
        "segments": req.segments,
        "confidence": req.confidence,
        "calibrated_confidence": req.calibrated_confidence,
        "risk_score": req.risk_score,
        "max_claim_risk": req.max_claim_risk,
        "agent_disagreement": req.agent_disagreement,
        "latency_ms": req.latency_ms,
        "total_tokens": req.total_tokens,
        "cost_usd": req.cost_usd,
        "pii_flags": req.pii_flags,
        "claims": [
            {"id": c.id, "text": c.text, "claim_type": c.claim_type, "criticality": c.criticality,
             "verdict": c.verdict, "risk_score": c.risk_score, "risk_level": c.risk_level,
             "risk_contributions": c.risk_contributions, "evidence": c.evidence}
            for c in claims
        ],
        "agent_runs": [
            {"agent": r.agent, "ordinal": r.ordinal, "output": r.output, "rationale": r.rationale,
             "latency_ms": r.latency_ms, "tokens": r.tokens, "model_version": r.model_version}
            for r in runs
        ],
        "claim_graph": (audit.trace.get("claim_graph") if audit else None),
        "model_versions": (audit.model_versions if audit else {}),
        "escalated": (audit.escalated if audit else False),
    }
