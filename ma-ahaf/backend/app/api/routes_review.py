"""Human-in-the-loop review queue for escalated / high-risk responses
(proposal §18 "audit trails for high-risk responses and human escalation",
§20 "human-in-the-loop review queues for high-impact claims").
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, requires
from app.core.errors import BadRequest, NotFound
from app.db import models
from app.db.repositories import get_audit
from app.db.session import get_db

router = APIRouter(prefix="/v1/review", tags=["human-review"])


class ResolveRequest(BaseModel):
    decision: Literal["approved", "revised", "rejected"]
    note: str = ""
    revised_response: str | None = None


@router.get("/queue")
def queue(
    principal: Principal = Depends(requires("operator")),
    db: Session = Depends(get_db),
    status: Literal["pending", "reviewed", "all"] = "pending",
) -> list[dict]:
    Q, R = models.EscalationQueue, models.Request
    stmt = (
        select(Q, R.prompt, R.action, R.calibrated_confidence, R.max_claim_risk,
               R.agent_disagreement, R.task_type)
        .join(R, R.id == Q.request_id)
        .where(Q.tenant_id == principal.tenant_id)
        .order_by(Q.created_at.desc())
    )
    if status != "all":
        stmt = stmt.where(Q.status == status)
    rows = db.execute(stmt).all()
    return [
        {
            "id": q.id, "request_id": q.request_id, "reason": q.reason, "status": q.status,
            "created_at": q.created_at.isoformat(), "prompt": prompt[:240], "action": action,
            "calibrated_confidence": conf, "max_claim_risk": risk,
            "agent_disagreement": disag, "task_type": ttype,
            "reviewed_by": q.reviewed_by, "decision": q.decision,
        }
        for q, prompt, action, conf, risk, disag, ttype in rows
    ]


@router.get("/queue/stats")
def stats(
    principal: Principal = Depends(requires("operator")),
    db: Session = Depends(get_db),
) -> dict:
    Q = models.EscalationQueue
    rows = db.execute(
        select(Q.status, func.count()).where(Q.tenant_id == principal.tenant_id).group_by(Q.status)
    ).all()
    by_status = dict(rows)
    return {"pending": by_status.get("pending", 0), "reviewed": by_status.get("reviewed", 0)}


@router.get("/queue/{item_id}")
def review_item(
    item_id: str,
    principal: Principal = Depends(requires("operator")),
    db: Session = Depends(get_db),
) -> dict:
    q = db.get(models.EscalationQueue, item_id)
    if q is None or q.tenant_id != principal.tenant_id:
        raise NotFound("review item not found")
    req = db.get(models.Request, q.request_id)
    audit = get_audit(db, principal.tenant_id, q.request_id)
    claims = db.scalars(
        select(models.Claim).where(models.Claim.request_id == q.request_id)
        .order_by(models.Claim.ordinal)
    ).all()
    return {
        "id": q.id, "request_id": q.request_id, "reason": q.reason, "status": q.status,
        "decision": q.decision, "review_note": q.review_note, "reviewed_by": q.reviewed_by,
        "prompt": req.prompt if req else None,
        "final_response": req.final_response if req else None,
        "action": req.action if req else None,
        "policy_vector": req.policy_vector if req else {},
        "calibrated_confidence": req.calibrated_confidence if req else None,
        "max_claim_risk": req.max_claim_risk if req else None,
        "agent_disagreement": req.agent_disagreement if req else None,
        "claims": [
            {"text": c.text, "claim_type": c.claim_type, "verdict": c.verdict,
             "risk_score": c.risk_score, "risk_level": c.risk_level,
             "risk_contributions": c.risk_contributions, "evidence": c.evidence}
            for c in claims
        ],
        "claim_graph": audit.trace.get("claim_graph") if audit else None,
        "model_versions": audit.model_versions if audit else {},
    }


@router.post("/queue/{item_id}/resolve")
def resolve(
    item_id: str,
    body: ResolveRequest,
    principal: Principal = Depends(requires("operator")),
    db: Session = Depends(get_db),
) -> dict:
    q = db.get(models.EscalationQueue, item_id)
    if q is None or q.tenant_id != principal.tenant_id:
        raise NotFound("review item not found")
    if q.status == "reviewed":
        raise BadRequest("already reviewed")
    if body.decision == "revised" and not body.revised_response:
        raise BadRequest("revised_response is required when decision is 'revised'")

    q.status = "reviewed"
    q.decision = body.decision
    q.review_note = body.note
    q.reviewed_by = principal.subject
    q.reviewed_at = datetime.now(UTC)

    req = db.get(models.Request, q.request_id)
    if req is not None:
        if body.decision == "revised":
            req.final_response = body.revised_response
            req.action = "answer"
        elif body.decision == "rejected":
            req.final_response = (
                "This response was reviewed and withheld by a human reviewer.\n\n"
                f"Reviewer note: {body.note}" if body.note else
                "This response was reviewed and withheld by a human reviewer."
            )
            req.action = "abstain"
        elif body.decision == "approved":
            req.action = "answer"
        # append the human decision to the audit trace
        audit = get_audit(db, principal.tenant_id, q.request_id)
        if audit is not None:
            trace = dict(audit.trace)
            trace["human_review"] = {
                "decision": body.decision, "note": body.note,
                "reviewed_by": principal.subject, "reviewed_at": q.reviewed_at.isoformat(),
            }
            audit.trace = trace

    return {"id": q.id, "status": q.status, "decision": q.decision}
