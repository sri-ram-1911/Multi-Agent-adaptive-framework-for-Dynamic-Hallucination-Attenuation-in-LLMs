"""Pipeline runner — constructs the request state, executes the orchestration
flow, persists the audit trail, and returns the API response payload.

The canonical flow graph lives in `graph.py` (LangGraph, used for visualisation
and as the architecture deliverable). This runner executes the same nodes with an
explicit, debuggable control loop so state merging is never ambiguous.
"""

from __future__ import annotations

import time
import uuid

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.security import redact_pii
from app.core.telemetry import REQUEST_LATENCY, REQUESTS
from app.db.repositories import persist_request
from app.llm.gateway import Gateway, UsageMeter
from app.orchestration import nodes as N
from app.orchestration.nodes import needs_revision
from app.orchestration.state import RequestState

log = get_logger("pipeline")


def run_pipeline(
    db: Session,
    *,
    tenant_id: str,
    prompt: str,
    context: str | None = None,
    policy_profile: str = "balanced",
    policy_overrides: dict[str, float] | None = None,
    persist: bool = True,
) -> RequestState:
    t0 = time.perf_counter()
    redacted, pii_flags = redact_pii(prompt)
    redacted_ctx, ctx_flags = redact_pii(context or "")

    meter = UsageMeter()
    state = RequestState(
        request_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        prompt=redacted,
        raw_prompt=prompt,
        context=redacted_ctx or None,
        policy_profile=policy_profile,
        policy_overrides=policy_overrides or {},
        pii_flags=sorted(set(pii_flags) | set(ctx_flags)),
    )
    state.db = db
    state.gateway = Gateway(meter)

    from app.nlp import nli as _nli

    _nli.set_gateway(state.gateway)  # enables the LLM-backed NLI path

    # --- input intelligence + adaptive control ---
    N.n_intent(state)
    N.n_risk(state)
    N.n_policy(state)

    # --- generation + claim analysis ---
    N.n_pre_retrieve(state)
    N.n_generate(state)
    N.n_decompose(state)

    # --- evidence + verification, with bounded revision loop ---
    from app.config import settings as _s

    for _ in range(_s.max_revision_loops + 2):  # hard ceiling; never spin
        N.n_retrieve(state)
        N.n_verify(state)
        N.n_risk_scoring(state)
        N.n_creativity(state)
        if needs_revision(state) == "revise":
            N.n_revise(state)
            N.n_decompose(state)
            continue
        break

    # --- resolution + response control ---
    N.n_decide(state)
    N.n_finalize(state)

    latency_ms = int((time.perf_counter() - t0) * 1000)
    REQUEST_LATENCY.observe(latency_ms / 1000)
    REQUESTS.labels(action=state.action).inc()

    if persist:
        _persist(db, state, meter, latency_ms)

    log.info(
        "pipeline.done", request_id=state.request_id, action=state.action,
        latency_ms=latency_ms, tokens=meter.total_tokens, cost_usd=round(meter.cost_usd, 5),
        max_claim_risk=round(state.claim_graph.max_risk(), 3),
    )
    state.__dict__["_latency_ms"] = latency_ms
    state.__dict__["_usage"] = meter
    return state


def _persist(db: Session, state: RequestState, meter: UsageMeter, latency_ms: int) -> None:
    cg = state.claim_graph
    claims = [
        {
            "text": c.text, "claim_type": c.claim_type, "criticality": c.criticality,
            "risk_score": c.risk_score, "risk_level": c.risk_level,
            "risk_contributions": c.risk_contributions, "verdict": c.verdict,
            "evidence": [
                {"chunk_id": cid,
                 "entailment": c.entailment_score, "contradiction": c.contradiction_score}
                for cid in c.evidence_ids
            ],
        }
        for c in cg.claims
    ]
    agent_runs = [
        {"agent": r.agent, "output": r.output, "rationale": r.rationale,
         "latency_ms": r.latency_ms, "tokens": r.tokens, "model_version": r.model_version}
        for r in state.records
    ]
    persist_request(
        db,
        {
            "id": state.request_id,
            "tenant_id": state.tenant_id,
            "prompt": state.prompt,
            "task_type": state.task_type,
            "risk_score": state.risk_score,
            "policy_vector": state.policy.model_dump() if state.policy else {},
            "final_response": state.final_response,
            "segments": [s.model_dump() for s in state.segments],
            "confidence": state.confidence,
            "calibrated_confidence": state.calibrated_confidence,
            "action": state.action,
            "max_claim_risk": cg.max_risk(),
            "agent_disagreement": state.agent_disagreement,
            "latency_ms": latency_ms,
            "total_tokens": meter.total_tokens,
            "cost_usd": round(meter.cost_usd, 6),
            "pii_flags": state.pii_flags,
            "claims": claims,
            "agent_runs": agent_runs,
            "audit": {
                "trace": state.__dict__.get("_audit_trace", {}),
                "model_versions": state.model_versions,
                "escalated": state.__dict__.get("_escalated", False),
            },
        },
    )
