"""Auth (API key + JWT), RBAC, and PII redaction."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Literal

from jose import JWTError, jwt

from app.config import settings
from app.core.errors import Unauthorized

Role = Literal["admin", "operator", "viewer"]
ROLE_RANK: dict[str, int] = {"viewer": 0, "operator": 1, "admin": 2}


def create_access_token(subject: str, role: Role, tenant_id: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "role": role,
        "tenant_id": tenant_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:  # pragma: no cover
        raise Unauthorized("invalid or expired token") from exc


def require_role(user_role: str, minimum: Role) -> None:
    if ROLE_RANK.get(user_role, -1) < ROLE_RANK[minimum]:
        raise Unauthorized(f"role '{minimum}' required")


# ---- PII redaction (basic, extend with Presidio for production) ----
_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
    ("PHONE", re.compile(r"(?<!\d)(\+?\d[\d\s().-]{7,}\d)(?!\d)")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
]


def redact_pii(text: str) -> tuple[str, list[str]]:
    """Return (redacted_text, list_of_types_found). No-op if disabled."""
    if not settings.pii_redaction or not text:
        return text, []
    found: list[str] = []
    out = text
    for label, pat in _PII_PATTERNS:
        if pat.search(out):
            found.append(label)
            out = pat.sub(f"[{label}_REDACTED]", out)
    return out, found
