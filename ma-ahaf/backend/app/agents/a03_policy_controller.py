"""Agent 3 — Policy Controller / ARCOP (proposal §7, §8).

Turns the request signals into a policy vector and applies any caller overrides
(clamped) plus the tenant policy profile.
"""

from __future__ import annotations

import numpy as np

from app.agents.base import Agent
from app.controller.arcop import Signals, policy
from app.orchestration.state import RequestState


class PolicyController(Agent):
    name = "policy_controller"
    number = 3

    def _run(self, state: RequestState):
        signals = Signals(
            risk=state.risk_score,
            task_type=state.task_type,
            ambiguity=state.ambiguity,
            criticality=0.5 + 0.5 * state.risk_score,
            evidence_coverage=0.5,     # not yet known; refined after retrieval
            source_agreement=0.5,
            model_confidence=0.6,
        )
        pv = policy(signals, profile=state.policy_profile)

        for key, val in state.policy_overrides.items():
            if hasattr(pv, key):
                # overrides may loosen at most 0.3 from the computed safe value
                base = getattr(pv, key)
                setattr(pv, key, float(np.clip(val, base - 0.3, 1.0)))

        state.signals = signals
        state.policy = pv
        return (
            {"policy_vector": pv.model_dump(), "overrides_applied": list(state.policy_overrides)},
            pv.rationale,
            "arcop/v1",
        )
