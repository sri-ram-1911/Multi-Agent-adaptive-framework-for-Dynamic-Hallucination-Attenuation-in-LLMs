"""JSON metrics for the dashboard (Prometheus text is served at /metrics)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, requires
from app.db import models
from app.db.session import get_db

router = APIRouter(prefix="/v1/metrics", tags=["observability"])


@router.get("/summary")
def summary(
    principal: Principal = Depends(requires("viewer")),
    db: Session = Depends(get_db),
    hours: int = 24 * 7,
) -> dict:
    since = datetime.now(UTC) - timedelta(hours=hours)
    R = models.Request
    base = select(R).where(R.tenant_id == principal.tenant_id, R.created_at >= since)
    rows = list(db.scalars(base))
    n = len(rows) or 1

    by_action: dict[str, int] = {}
    for r in rows:
        by_action[r.action or "?"] = by_action.get(r.action or "?", 0) + 1

    lat = sorted(r.latency_ms or 0 for r in rows)
    p = lambda q: lat[min(len(lat) - 1, int(q * len(lat)))] if lat else 0  # noqa: E731

    depth_hist = db.execute(
        select(func.jsonb_extract_path_text(R.policy_vector, "verification_depth"))
        .where(R.tenant_id == principal.tenant_id, R.created_at >= since)
    ).all()
    depths = [float(d[0]) for d in depth_hist if d[0] is not None]

    return {
        "window_hours": hours,
        "total_requests": len(rows),
        "by_action": by_action,
        "abstention_rate": round((by_action.get("abstain", 0) + by_action.get("escalate", 0)) / n, 3),
        "avg_calibrated_confidence": round(
            sum(r.calibrated_confidence or 0 for r in rows) / n, 3
        ),
        "avg_max_claim_risk": round(sum(r.max_claim_risk or 0 for r in rows) / n, 3),
        "avg_agent_disagreement": round(sum(r.agent_disagreement or 0 for r in rows) / n, 3),
        "latency_ms": {"p50": p(0.5), "p90": p(0.9), "p95": p(0.95)},
        "tokens_total": sum(r.total_tokens or 0 for r in rows),
        "cost_usd_total": round(sum(r.cost_usd or 0 for r in rows), 4),
        "avg_verification_depth": round(sum(depths) / len(depths), 3) if depths else None,
        "timeseries": [
            {"t": r.created_at.isoformat(), "latency_ms": r.latency_ms,
             "risk": r.max_claim_risk, "confidence": r.calibrated_confidence,
             "action": r.action}
            for r in sorted(rows, key=lambda x: x.created_at)
        ],
    }


@router.get("/escalations")
def escalations(
    principal: Principal = Depends(requires("operator")),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(
        select(models.EscalationQueue)
        .where(models.EscalationQueue.tenant_id == principal.tenant_id,
               models.EscalationQueue.status == "pending")
        .order_by(models.EscalationQueue.created_at.desc())
    ).all()
    return [
        {"id": r.id, "request_id": r.request_id, "reason": r.reason,
         "created_at": r.created_at.isoformat()}
        for r in rows
    ]
