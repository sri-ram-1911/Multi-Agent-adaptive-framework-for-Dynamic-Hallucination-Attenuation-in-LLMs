"""Thin persistence helpers used by the API and orchestration layer."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models


def get_tenant_by_name(db: Session, name: str) -> models.Tenant | None:
    return db.scalar(select(models.Tenant).where(models.Tenant.name == name))


def get_api_key(db: Session, key_hash: str) -> models.ApiKey | None:
    return db.scalar(
        select(models.ApiKey).where(
            models.ApiKey.key_hash == key_hash, models.ApiKey.active.is_(True)
        )
    )


def persist_request(db: Session, payload: dict[str, Any]) -> models.Request:
    claims = payload.pop("claims", [])
    agent_runs = payload.pop("agent_runs", [])
    audit = payload.pop("audit", None)
    req = models.Request(**payload)
    db.add(req)
    db.flush()

    for i, c in enumerate(claims):
        db.add(models.Claim(request_id=req.id, ordinal=i, **c))
    for i, a in enumerate(agent_runs):
        db.add(models.AgentRun(request_id=req.id, ordinal=i, **a))
    if audit is not None:
        db.add(
            models.AuditTrace(
                request_id=req.id,
                tenant_id=req.tenant_id,
                trace=audit.get("trace", {}),
                model_versions=audit.get("model_versions", {}),
                escalated=audit.get("escalated", False),
            )
        )
    if payload.get("action") == "escalate":
        db.add(
            models.EscalationQueue(
                request_id=req.id, tenant_id=req.tenant_id, reason="agent_disagreement_or_high_risk"
            )
        )
    db.flush()
    return req


def list_requests(db: Session, tenant_id: str, *, limit: int = 50, action: str | None = None):
    q = select(models.Request).where(models.Request.tenant_id == tenant_id)
    if action:
        q = q.where(models.Request.action == action)
    q = q.order_by(models.Request.created_at.desc()).limit(limit)
    return list(db.scalars(q))


def get_request(db: Session, tenant_id: str, request_id: str) -> models.Request | None:
    return db.scalar(
        select(models.Request).where(
            models.Request.id == request_id, models.Request.tenant_id == tenant_id
        )
    )


def get_audit(db: Session, tenant_id: str, request_id: str) -> models.AuditTrace | None:
    return db.scalar(
        select(models.AuditTrace).where(
            models.AuditTrace.request_id == request_id,
            models.AuditTrace.tenant_id == tenant_id,
        )
    )
