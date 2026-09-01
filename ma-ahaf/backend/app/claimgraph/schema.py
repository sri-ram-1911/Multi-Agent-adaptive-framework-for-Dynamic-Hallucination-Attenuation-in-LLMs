"""Claim Risk Graph data types (proposal §5 'Claim Risk Graph')."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ClaimType = Literal["factual", "numeric", "causal", "temporal", "opinion", "creative"]
Verdict = Literal["supported", "refuted", "insufficient", "unverified"]


class Claim(BaseModel):
    id: str
    ordinal: int
    text: str
    claim_type: ClaimType = "factual"
    criticality: float = 0.5          # how much this claim matters to the answer
    temporal_sensitivity: float = 0.0
    entities: list[str] = Field(default_factory=list)
    span: tuple[int, int] | None = None   # char offsets in the candidate answer

    # filled by verification / risk model
    verdict: Verdict = "unverified"
    entailment_score: float = 0.0     # max entailment prob over evidence
    contradiction_score: float = 0.0
    evidence_coverage: float = 0.0
    source_agreement: float = 0.0
    model_uncertainty: float = 0.5
    agent_disagreement: float = 0.0
    risk_score: float = 0.0
    risk_level: Literal["low", "medium", "high"] = "low"
    risk_contributions: dict[str, float] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)


class ClaimGraph(BaseModel):
    claims: list[Claim] = Field(default_factory=list)
    # edges: claim_id -> list of claim_ids it depends on
    dependencies: dict[str, list[str]] = Field(default_factory=dict)

    def max_risk(self) -> float:
        return max((c.risk_score for c in self.claims), default=0.0)

    def critical_unsupported(self) -> list[Claim]:
        return [
            c for c in self.claims
            if c.criticality >= 0.5 and c.verdict in ("refuted", "insufficient")
        ]
