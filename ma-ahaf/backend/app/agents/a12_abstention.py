"""Agent 12 — Abstention / Escalation Agent (proposal §7).

Decides the final safety action: answer / qualify / abstain / escalate, using the
calibrated confidence, the hallucination budget, claim-level risk, agent
disagreement and the policy thresholds.
"""

from __future__ import annotations

import re

from app.agents.base import Agent
from app.controller import budget, calibration
from app.controller.consensus import request_disagreement
from app.orchestration.state import RequestState, ResponseSegment

_CITATION_ONLY = re.compile(r"^[\s,.;:\[\]S0-9()-]*$", re.I)


def _is_degenerate(text: str) -> bool:
    """A response that carries no information (empty, citation markers only, a
    stray fragment). Never answer confidently on one of these."""
    t = (text or "").strip()
    if len(t) < 25:
        return True
    if _CITATION_ONLY.match(t):
        return True
    return len(re.findall(r"[a-zA-Z]{3,}", t)) < 5


def _segment(state: RequestState) -> list[ResponseSegment]:
    """Split the answer into factual / assumption / creative segments (proposal §10)."""
    cg = state.claim_graph
    segs: list[ResponseSegment] = []
    for c in cg.claims:
        kind = (
            "creative" if c.claim_type == "creative"
            else "assumption" if c.claim_type == "opinion" or c.verdict in ("insufficient", "unverified")
            else "factual"
        )
        segs.append(
            ResponseSegment(
                kind=kind, text=c.text, claim_ids=[c.id],
                supported=(c.verdict == "supported") if kind == "factual" else None,
            )
        )
    return segs


class Abstention(Agent):
    name = "abstention"
    number = 12

    def _run(self, state: RequestState):
        cg = state.claim_graph
        pv = state.policy

        supported = [c for c in cg.claims if c.verdict == "supported"]
        checkable = [c for c in cg.claims if c.claim_type not in ("creative", "opinion")]

        degenerate = _is_degenerate(state.chosen_candidate)
        substantive_prompt = len(state.prompt.split()) >= 4
        # a substantive prompt that produced no checkable claims => uninformative answer
        empty_analysis = substantive_prompt and not cg.claims and state.task_type != "creative"
        # best retrieval relevance actually seen (rerank score, else vector score)
        best_ev = max(
            (e.rerank_score if e.rerank_score else e.vector_score for e in state.evidence),
            default=0.0,
        )
        # If NOTHING retrieved is on-topic, a claim can still be "supported" by a
        # passage that merely entails a vague sentence — that is not real grounding.
        # For non-creative requests, no relevant passage => abstain regardless.
        weak_evidence = (
            bool(state.evidence)
            and best_ev <= 0.0
            and state.task_type not in ("creative",)
        )

        if checkable:
            evidence_strength = sum(c.entailment_score for c in checkable) / len(checkable)
        elif state.task_type == "creative":
            evidence_strength = 1.0
        else:
            evidence_strength = 0.0

        if degenerate or empty_analysis or weak_evidence:
            evidence_strength = min(evidence_strength, 0.15)

        raw_conf = (
            0.35 * state.signals.model_confidence
            + 0.40 * evidence_strength
            + 0.25 * (1.0 - cg.max_risk())
        )
        if degenerate:
            raw_conf = min(raw_conf, 0.15)
        calibrated = calibration.calibrate(raw_conf)
        gap = calibration.consistency_gap(raw_conf, evidence_strength)

        disagreement = request_disagreement(cg.claims)
        over, used, limit = budget.over_budget(cg, state.task_type, state.signals.criticality)
        critical_unsupported = cg.critical_unsupported()

        # decision
        if degenerate or empty_analysis:
            action, reason = "abstain", (
                "the generated answer contains no verifiable content"
                if degenerate else
                "no checkable claims could be extracted from the answer for this request"
            )
        elif weak_evidence:
            action, reason = "abstain", (
                f"no retrieved passage is relevant to the request (best relevance {best_ev:.2f})"
            )
        elif disagreement >= pv.escalation_threshold or (over and state.task_type == "high_stakes"):
            action, reason = "escalate", (
                f"agent disagreement {disagreement:.2f} >= {pv.escalation_threshold:.2f}"
                if disagreement >= pv.escalation_threshold
                else f"hallucination budget exceeded on high-stakes task ({used:.2f}>{limit:.2f})"
            )
        elif calibrated < pv.abstention_threshold and critical_unsupported:
            action, reason = "abstain", (
                f"calibrated confidence {calibrated:.2f} < threshold {pv.abstention_threshold:.2f} "
                f"with {len(critical_unsupported)} critical unsupported claim(s)"
            )
        elif critical_unsupported or over or gap > 0.25:
            action, reason = "qualify", (
                "answer delivered with explicit uncertainty: "
                + (f"{len(critical_unsupported)} claims lack sufficient evidence; " if critical_unsupported else "")
                + (f"confidence-evidence gap {gap:.2f}; " if gap > 0.25 else "")
                + (f"risk budget {used:.2f}/{limit:.2f}" if over else "")
            ).strip()
        else:
            action, reason = "answer", "evidence sufficient and consistent"

        state.evidence_strength = round(evidence_strength, 3)
        state.agent_disagreement = round(disagreement, 3)
        state.confidence = round(raw_conf, 3)
        state.calibrated_confidence = round(calibrated, 3)
        state.consistency_gap = round(gap, 3)
        state.action = action
        state.action_reason = reason
        state.segments = _segment(state)

        return (
            {"action": action, "reason": reason, "raw_confidence": state.confidence,
             "calibrated_confidence": state.calibrated_confidence,
             "consistency_gap": state.consistency_gap, "disagreement": state.agent_disagreement,
             "budget_used": round(used, 3), "budget_limit": round(limit, 3),
             "supported_claims": len(supported), "critical_unsupported": len(critical_unsupported)},
            reason,
            "abstention/v1",
        )
