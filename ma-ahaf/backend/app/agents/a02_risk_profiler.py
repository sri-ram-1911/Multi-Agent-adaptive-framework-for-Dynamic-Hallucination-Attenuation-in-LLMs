"""Agent 2 — Risk Profiler (proposal §7).

Estimates request-level consequence, ambiguity, domain risk and hallucination
susceptibility -> a single risk score in [0,1] plus its factor breakdown.

Interpretable scorer over engineered features; `app.ml.train_policy`-style
retraining on labelled incidents is the documented upgrade path.
"""

from __future__ import annotations

import re

from app.agents.base import Agent
from app.nlp.zeroshot import classify
from app.orchestration.state import RequestState

_HIGH_RISK_DOMAINS = {
    "medical": ["dose", "mg", "symptom", "diagnos", "treatment", "drug", "contraindicat"],
    "legal": ["contract", "clause", "liable", "statute", "regulation", "gdpr", "compliance"],
    "financial": ["invest", "returns", "tax", "valuation", "portfolio", "forecast", "revenue"],
    "safety": ["hazard", "toxic", "voltage", "structural", "emergency"],
}
_CONSEQUENCE = ["harmless", "consequential decision", "safety-critical or legally binding"]
_NUM_RE = re.compile(r"\b\d[\d,.]*\b")


class RiskProfiler(Agent):
    name = "risk_profiler"
    number = 2

    def _run(self, state: RequestState):
        text = (state.prompt + " " + (state.context or "")).lower()

        domain_hits = {
            d: sum(k in text for k in kws) for d, kws in _HIGH_RISK_DOMAINS.items()
        }
        domain_risk = min(1.0, max(domain_hits.values()) / 3) if domain_hits else 0.0

        consequence = classify(state.prompt, _CONSEQUENCE)
        consequence_risk = (
            0.0 * consequence[_CONSEQUENCE[0]]
            + 0.6 * consequence[_CONSEQUENCE[1]]
            + 1.0 * consequence[_CONSEQUENCE[2]]
        )

        numeric_load = min(1.0, len(_NUM_RE.findall(state.prompt)) / 4)
        type_prior = {"high_stakes": 0.9, "factual": 0.45, "analytical": 0.5,
                      "mixed": 0.4, "creative": 0.1}.get(state.task_type, 0.4)

        factors = {
            "domain_risk": round(domain_risk, 3),
            "consequence": round(consequence_risk, 3),
            "ambiguity": round(state.ambiguity, 3),
            "numeric_load": round(numeric_load, 3),
            "task_prior": round(type_prior, 3),
        }
        risk = (
            0.30 * domain_risk
            + 0.28 * consequence_risk
            + 0.14 * state.ambiguity
            + 0.10 * numeric_load
            + 0.18 * type_prior
        )
        risk = round(min(1.0, risk), 4)

        state.risk_score = risk
        state.risk_factors = factors
        dominant = max(factors, key=factors.get)
        return (
            {"risk_score": risk, "factors": factors, "domain_hits": domain_hits},
            f"risk={risk:.2f}; dominant={dominant}",
            "risk-profiler/rules-v1",
        )
