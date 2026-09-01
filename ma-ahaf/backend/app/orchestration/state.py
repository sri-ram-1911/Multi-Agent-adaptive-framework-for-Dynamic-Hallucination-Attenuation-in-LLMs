"""RequestState — the single object threaded through the LangGraph state machine."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.claimgraph.schema import ClaimGraph
from app.controller.arcop import PolicyVector, Signals
from app.llm.gateway import Gateway
from app.retrieval.schema import Evidence


class AgentRecord(BaseModel):
    agent: str
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    rationale: str | None = None
    latency_ms: int = 0
    tokens: int = 0
    model_version: str | None = None


class ResponseSegment(BaseModel):
    kind: str  # "factual" | "assumption" | "creative"
    text: str
    claim_ids: list[str] = Field(default_factory=list)
    supported: bool | None = None


class RequestState(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    # inputs
    request_id: str
    tenant_id: str
    prompt: str
    raw_prompt: str
    context: str | None = None
    policy_profile: str = "balanced"
    policy_overrides: dict[str, float] = Field(default_factory=dict)
    pii_flags: list[str] = Field(default_factory=list)

    # runtime handles (not serialised into the trace)
    db: Session | None = Field(default=None, exclude=True)
    gateway: Gateway | None = Field(default=None, exclude=True)

    # agent outputs
    task_type: str = "factual"
    ambiguity: float = 0.3
    risk_score: float = 0.5
    risk_factors: dict[str, float] = Field(default_factory=dict)
    signals: Signals | None = None
    policy: PolicyVector | None = None

    candidates: list[str] = Field(default_factory=list)
    chosen_candidate: str = ""
    claim_graph: ClaimGraph = Field(default_factory=ClaimGraph)
    evidence: list[Evidence] = Field(default_factory=list)

    creativity_score: float = 0.0
    creative_spans: list[tuple[int, int]] = Field(default_factory=list)
    evidence_strength: float = 0.0
    agent_disagreement: float = 0.0

    revised: bool = False
    revision_loops: int = 0

    # final
    final_response: str = ""
    segments: list[ResponseSegment] = Field(default_factory=list)
    confidence: float = 0.0
    calibrated_confidence: float = 0.0
    consistency_gap: float = 0.0
    action: str = "answer"          # answer | qualify | abstain | escalate
    action_reason: str = ""

    # trace
    records: list[AgentRecord] = Field(default_factory=list)
    model_versions: dict[str, str] = Field(default_factory=dict)

    def add_record(self, rec: AgentRecord) -> None:
        self.records.append(rec)
        if rec.model_version:
            self.model_versions[rec.agent] = rec.model_version
