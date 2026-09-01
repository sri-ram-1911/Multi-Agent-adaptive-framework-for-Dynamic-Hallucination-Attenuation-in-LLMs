"""API request/response models (OpenAPI schemas)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    context: str | None = Field(None, max_length=20000)
    policy_profile: str = Field("balanced", description="strict | balanced | creative")
    policy_overrides: dict[str, float] = Field(
        default_factory=dict,
        description="Loosen (bounded) any policy-vector field, e.g. {\"creativity_allowance\": 0.9}",
    )


class EvidenceOut(BaseModel):
    chunk_id: str
    document_title: str
    source: str
    text: str
    source_score: float
    rerank_score: float
    stance: str


class ClaimOut(BaseModel):
    id: str
    text: str
    claim_type: str
    criticality: float
    verdict: str
    risk_score: float
    risk_level: str
    risk_contributions: dict[str, float]
    evidence_ids: list[str]
    explanation: str


class SegmentOut(BaseModel):
    kind: str
    text: str
    supported: bool | None = None


class GenerateResponse(BaseModel):
    trace_id: str
    response: str
    segments: list[SegmentOut]
    action: str
    action_reason: str
    confidence: float
    calibrated_confidence: float
    consistency_gap: float
    task_type: str
    risk_score: float
    max_claim_risk: float
    agent_disagreement: float
    creativity_score: float
    policy_vector: dict
    claims: list[ClaimOut]
    evidence: list[EvidenceOut]
    usage: dict
    latency_ms: int


class TokenRequest(BaseModel):
    tenant: str
    role: str = "operator"


class KBDocumentIn(BaseModel):
    title: str
    source: str = "doc"
    text: str
    authority: float = 0.5
    uri: str | None = None
    published_at: str | None = None


class KBSearchRequest(BaseModel):
    query: str
    k: int = 5
