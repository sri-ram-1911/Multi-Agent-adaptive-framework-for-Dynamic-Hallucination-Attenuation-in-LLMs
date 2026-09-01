"""Auth / RBAC / tenant-isolation dependencies."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import Unauthorized
from app.core.ratelimit import check_rate_limit
from app.core.security import Role, decode_token, require_role
from app.db.repositories import get_api_key, get_tenant_by_name
from app.db.session import get_db


@dataclass
class Principal:
    tenant_id: str
    tenant_name: str
    role: str
    subject: str


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def get_principal(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Principal:
    # 1) API key
    if x_api_key:
        await check_rate_limit(_hash_key(x_api_key))
        if x_api_key == settings.dev_api_key:
            tenant = get_tenant_by_name(db, "default")
            if tenant is None:
                raise Unauthorized("default tenant not seeded; run `make seed`")
            return Principal(tenant.id, tenant.name, "admin", "dev-api-key")
        rec = get_api_key(db, _hash_key(x_api_key))
        if rec is None:
            raise Unauthorized("invalid api key")
        from app.db.models import Tenant

        t = db.get(Tenant, rec.tenant_id)
        return Principal(rec.tenant_id, t.name if t else "unknown", rec.role, rec.label)

    # 2) JWT (dashboard users)
    if authorization and authorization.lower().startswith("bearer "):
        payload = decode_token(authorization.split(" ", 1)[1])
        return Principal(
            payload["tenant_id"], payload.get("tenant_name", ""), payload["role"], payload["sub"]
        )

    raise Unauthorized("provide x-api-key or Bearer token")


def requires(minimum: Role):
    async def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        require_role(principal.role, minimum)
        return principal

    return _dep
