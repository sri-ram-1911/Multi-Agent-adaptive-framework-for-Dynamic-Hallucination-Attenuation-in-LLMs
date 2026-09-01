"""Adaptive Reliability-Creativity Operating Point controller (proposal §8).

Computes a *policy vector* per request:
    π = f(Risk, Intent, EvidenceCoverage, ClaimCriticality, Ambiguity,
          SourceAgreement, CreativityDemand, ModelConfidence, Cost, Latency)

Default is the interpretable rule/scoring engine below. If a trained policy
artifact exists (`app/ml/train_policy.py`) it is blended in (learning-to-route),
clamped by the rule engine so a bad model can never disable safety behaviour.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, Field

from app.ml import registry
from app.ml.features import POLICY_INPUTS

# named policy profiles (tenant default; see proposal §10 control strategy table)
PROFILES: dict[str, dict[str, float]] = {
    "strict":   {"grounding": 0.15, "verify": 0.20, "creativity": -0.10, "citation": 0.20, "abstain": 0.10},
    "balanced": {"grounding": 0.00, "verify": 0.00, "creativity": 0.00, "citation": 0.00, "abstain": 0.00},
    "creative": {"grounding": -0.15, "verify": -0.15, "creativity": 0.20, "citation": -0.15, "abstain": -0.05},
}

_INTENT_CREATIVITY = {
    "factual": 0.05, "analytical": 0.25, "creative": 0.95, "mixed": 0.55, "high_stakes": 0.0,
}


class PolicyVector(BaseModel):
    grounding_intensity: float = Field(0.5, ge=0, le=1)
    verification_depth: float = Field(0.5, ge=0, le=1)   # 0 light · 0.5 standard · 1 deep
    creativity_allowance: float = Field(0.5, ge=0, le=1)
    citation_requirement: float = Field(0.5, ge=0, le=1)
    abstention_threshold: float = Field(0.5, ge=0, le=1) # min confidence to answer
    escalation_threshold: float = Field(0.7, ge=0, le=1) # disagreement/risk above -> human
    candidates: int = 2
    rationale: str = ""

    @property
    def depth_bucket(self) -> int:
        return 0 if self.verification_depth < 0.34 else (1 if self.verification_depth < 0.67 else 2)


class Signals(BaseModel):
    risk: float = 0.5
    task_type: str = "factual"
    ambiguity: float = 0.3
    criticality: float = 0.5
    creativity_demand: float | None = None
    evidence_coverage: float = 0.5
    source_agreement: float = 0.5
    model_confidence: float = 0.6
    cost_budget: float = 1.0     # 0 cheap .. 1 generous
    latency_budget: float = 1.0

    def creativity(self) -> float:
        if self.creativity_demand is not None:
            return self.creativity_demand
        return _INTENT_CREATIVITY.get(self.task_type, 0.2)


def _rule_policy(s: Signals) -> PolicyVector:
    cd = s.creativity()
    grounding = 0.35 + 0.45 * s.risk + 0.25 * s.criticality - 0.30 * cd
    verify = 0.20 + 0.55 * s.risk + 0.35 * s.criticality + 0.25 * (1 - s.source_agreement) - 0.30 * cd
    creativity = 0.15 + 0.80 * cd - 0.45 * s.risk - 0.30 * s.criticality
    citation = 0.20 + 0.65 * s.criticality + 0.40 * s.risk - 0.30 * cd
    abstain = 0.20 + 0.45 * s.criticality + 0.35 * s.risk - 0.30 * s.evidence_coverage
    escalate = 0.35 + 0.40 * s.risk + 0.30 * s.criticality

    # cost / latency pressure trims verification depth & candidate count
    verify -= 0.20 * (1 - s.cost_budget) + 0.15 * (1 - s.latency_budget)
    cands = 1 if (s.cost_budget < 0.4 or cd < 0.2) else (3 if cd > 0.7 else 2)

    clip = lambda x: float(np.clip(x, 0.0, 1.0))  # noqa: E731
    return PolicyVector(
        grounding_intensity=clip(grounding),
        verification_depth=clip(verify),
        creativity_allowance=clip(creativity),
        citation_requirement=clip(citation),
        abstention_threshold=clip(np.clip(abstain, 0.05, 0.9)),
        escalation_threshold=clip(np.clip(escalate, 0.1, 0.95)),
        candidates=cands,
        rationale=(
            f"risk={s.risk:.2f} crit={s.criticality:.2f} creativity_demand={cd:.2f} "
            f"coverage={s.evidence_coverage:.2f} agreement={s.source_agreement:.2f}"
        ),
    )


def _apply_profile(p: PolicyVector, profile: str) -> PolicyVector:
    adj = PROFILES.get(profile, PROFILES["balanced"])
    clip = lambda x: float(np.clip(x, 0.0, 1.0))  # noqa: E731
    return p.model_copy(
        update={
            "grounding_intensity": clip(p.grounding_intensity + adj["grounding"]),
            "verification_depth": clip(p.verification_depth + adj["verify"]),
            "creativity_allowance": clip(p.creativity_allowance + adj["creativity"]),
            "citation_requirement": clip(p.citation_requirement + adj["citation"]),
            "abstention_threshold": clip(p.abstention_threshold + adj["abstain"]),
        }
    )


def policy(s: Signals, *, profile: str = "balanced") -> PolicyVector:
    rule = _apply_profile(_rule_policy(s), profile)

    art = registry.load("policy.joblib")
    if art is None:
        return rule
    try:
        x = np.array([[s.risk, s.ambiguity, s.criticality, s.creativity(),
                       s.evidence_coverage, s.source_agreement, s.model_confidence]])
        assert len(POLICY_INPUTS) == x.shape[1]
        g, v, c, cit, ab, esc = art["model"].predict(x)[0]
        # blend 50/50, then re-clamp to never fall below the rule engine's safety floor
        # for verification / citation / abstention on risky requests.
        blend = lambda r, m: float(np.clip(0.5 * r + 0.5 * m, 0.0, 1.0))  # noqa: E731
        out = rule.model_copy(update={
            "grounding_intensity": blend(rule.grounding_intensity, g),
            "verification_depth": max(blend(rule.verification_depth, v),
                                      rule.verification_depth if s.risk > 0.6 else 0.0),
            "creativity_allowance": blend(rule.creativity_allowance, c),
            "citation_requirement": max(blend(rule.citation_requirement, cit),
                                        rule.citation_requirement if s.criticality > 0.6 else 0.0),
            "abstention_threshold": max(blend(rule.abstention_threshold, ab),
                                        rule.abstention_threshold if s.risk > 0.6 else 0.0),
            "escalation_threshold": blend(rule.escalation_threshold, esc),
        })
        out.rationale = rule.rationale + " | +learned-policy"
        return out
    except Exception:  # pragma: no cover
        return rule
