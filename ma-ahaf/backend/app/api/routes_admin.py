"""Admin: tenants, API keys, policy profiles, auth tokens."""

from __future__ import annotations

import hashlib
import secrets

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, requires
from app.api.schemas import TokenRequest
from app.core.errors import BadRequest, NotFound
from app.core.security import create_access_token
from app.db import models
from app.db.session import get_db

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.post("/tenants", status_code=201)
def create_tenant(
    name: str, profile: str = "balanced",
    _: Principal = Depends(requires("admin")),
    db: Session = Depends(get_db),
) -> dict:
    if db.scalar(select(models.Tenant).where(models.Tenant.name == name)):
        raise BadRequest("tenant exists")
    t = models.Tenant(name=name, policy_profile=profile)
    db.add(t)
    db.flush()
    return {"id": t.id, "name": t.name, "policy_profile": t.policy_profile}


@router.post("/api-keys", status_code=201)
def create_api_key(
    label: str, role: str = "operator",
    principal: Principal = Depends(requires("admin")),
    db: Session = Depends(get_db),
) -> dict:
    raw = "mak_" + secrets.token_urlsafe(24)
    db.add(models.ApiKey(
        tenant_id=principal.tenant_id, label=label, role=role,
        key_hash=hashlib.sha256(raw.encode()).hexdigest(),
    ))
    return {"api_key": raw, "label": label, "role": role, "note": "shown once"}


@router.put("/policy-profile")
def set_policy_profile(
    profile: str,
    principal: Principal = Depends(requires("admin")),
    db: Session = Depends(get_db),
) -> dict:
    if profile not in ("strict", "balanced", "creative"):
        raise BadRequest("profile must be strict|balanced|creative")
    t = db.get(models.Tenant, principal.tenant_id)
    if t is None:
        raise NotFound("tenant")
    t.policy_profile = profile
    return {"tenant": t.name, "policy_profile": profile}


@router.post("/token")
def issue_token(body: TokenRequest, db: Session = Depends(get_db)) -> dict:
    """Dev helper: mint a dashboard JWT for a tenant. Disabled in prod — wire an
    OIDC/SSO provider and exchange its token for a MA-AHAF JWT instead."""
    from app.config import settings
    from app.core.errors import Forbidden

    if settings.is_prod:
        raise Forbidden("token minting is disabled in prod; use the SSO integration")
    t = db.scalar(select(models.Tenant).where(models.Tenant.name == body.tenant))
    if t is None:
        raise NotFound("tenant not found")
    token = create_access_token(subject=f"user@{body.tenant}", role=body.role, tenant_id=t.id)
    return {"access_token": token, "token_type": "bearer"}
