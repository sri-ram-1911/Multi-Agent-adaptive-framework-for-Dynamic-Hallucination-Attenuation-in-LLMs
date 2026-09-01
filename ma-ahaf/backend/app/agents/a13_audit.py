"""Agent 13 — Audit Agent (proposal §7, §18).

Records decisions, evidence, agent votes and model versions into a single
structured trace object for reproducibility and governance. The assembled trace
is stashed on the state for the pipeline runner to persist.
"""

from __future__ import annotations

from app.agents.base import Agent
from app.claimgraph.graph import to_cytoscape
from app.orchestration.state import RequestState


class Audit(Agent):
    name = "audit"
    number = 13

    def _run(self, state: RequestState):
        cg = state.claim_graph
        trace = {
            "request_id": state.request_id,
            "task_type": state.task_type,
            "ambiguity": state.ambiguity,
            "risk_score": state.risk_score,
            "risk_factors": state.risk_factors,
            "policy_vector": state.policy.model_dump() if state.policy else {},
            "signals": state.signals.model_dump() if state.signals else {},
            "candidates": state.candidates,
            "chosen_candidate": state.chosen_candidate,
            "final_response": state.final_response,
            "revised": state.revised,
            "revision_loops": state.revision_loops,
            "claims": [c.model_dump() for c in cg.claims],
            "claim_graph": to_cytoscape(cg),
            "evidence": [e.model_dump() for e in state.evidence],
            "creativity_score": state.creativity_score,
            "confidence": state.confidence,
            "calibrated_confidence": state.calibrated_confidence,
            "consistency_gap": state.consistency_gap,
            "agent_disagreement": state.agent_disagreement,
            "action": state.action,
            "action_reason": state.action_reason,
            "pii_flags": state.pii_flags,
            "agent_runs": [r.model_dump() for r in state.records],
        }
        escalated = state.action == "escalate"
        state.__dict__["_audit_trace"] = trace
        state.__dict__["_escalated"] = escalated
        return (
            {"trace_bytes": len(str(trace)), "escalated": escalated,
             "n_agent_runs": len(state.records),
             "model_versions": dict(state.model_versions)},
            "audit trace assembled",
            "audit/v1",
        )
