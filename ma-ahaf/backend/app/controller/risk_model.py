"""Claim-level hallucination risk model H(x) (proposal §9).

Uses the trained logistic model when present (learned w1..w7), else the
proposal's linear formula with hand-set weights. Always returns per-feature
`contributions` so the dashboard can explain *why* a claim is high risk.
"""

from __future__ import annotations

import math

import numpy as np

from app.claimgraph.schema import Claim
from app.ml import registry
from app.ml.features import RISK_FEATURES, risk_vector

# fallback weights (proposal §9 intent) if no artifact
_W = np.array([1.6, 1.9, 1.1, 0.9, 1.3, 0.7, 1.4])
_B = -3.1


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def score_claim(claim: Claim) -> Claim:
    signals = {
        "evidence_coverage": claim.evidence_coverage,
        "contradiction_score": claim.contradiction_score,
        "source_agreement": claim.source_agreement,
        "model_uncertainty": claim.model_uncertainty,
        "criticality": claim.criticality,
        "temporal_sensitivity": claim.temporal_sensitivity,
        "agent_disagreement": claim.agent_disagreement,
    }
    x = risk_vector(signals)

    art = registry.load("risk_model.joblib")
    if art is not None:
        proba = float(art["model"].predict_proba(x.reshape(1, -1))[0, 1])
        w = np.asarray(list(art["coef"].values()))
    else:
        proba = _sigmoid(float(x @ _W) + _B)
        w = _W

    raw = w * x
    denom = np.abs(raw).sum() or 1.0
    contributions = {f: round(float(v / denom), 3) for f, v in zip(RISK_FEATURES, raw, strict=True)}

    claim.risk_score = round(proba, 4)
    claim.risk_contributions = contributions
    claim.risk_level = "high" if proba >= 0.6 else "medium" if proba >= 0.35 else "low"
    return claim


def explain(claim: Claim) -> str:
    top = sorted(claim.risk_contributions.items(), key=lambda kv: kv[1], reverse=True)[:2]
    reasons = ", ".join(f"{k} ({v:+.2f})" for k, v in top)
    return f"risk={claim.risk_score:.2f} ({claim.risk_level}); dominant factors: {reasons}"
