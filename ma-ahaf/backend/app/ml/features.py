"""Feature extraction shared by training scripts and runtime inference."""

from __future__ import annotations

import numpy as np

# Order matters — these correspond to w1..w7 in proposal §9:
#   H(x) = w1(1-EvidenceCoverage) + w2 Contradiction + w3 SourceRisk
#        + w4 ModelUncertainty + w5 ClaimCriticality + w6 TemporalSensitivity
#        + w7 AgentDisagreement
RISK_FEATURES = [
    "missing_evidence",     # 1 - evidence_coverage
    "contradiction",        # contradiction_score
    "source_risk",          # 1 - source_agreement
    "model_uncertainty",    # avg (1 - token logprob) proxy
    "claim_criticality",    # how load-bearing the claim is
    "temporal_sensitivity", # dated facts decay
    "agent_disagreement",   # spread of verifier verdicts
]


def risk_vector(signals: dict[str, float]) -> np.ndarray:
    return np.array(
        [
            1.0 - signals.get("evidence_coverage", 0.0),
            signals.get("contradiction_score", 0.0),
            1.0 - signals.get("source_agreement", 0.5),
            signals.get("model_uncertainty", 0.5),
            signals.get("criticality", 0.5),
            signals.get("temporal_sensitivity", 0.0),
            signals.get("agent_disagreement", 0.0),
        ],
        dtype=np.float64,
    )


CLAIM_TYPES = ["factual", "numeric", "causal", "temporal", "opinion", "creative"]

SOURCE_FEATURES = ["authority", "freshness", "relevance", "consistency", "corroboration"]


def source_vector(feat: dict[str, float]) -> np.ndarray:
    return np.array([feat.get(k, 0.5) for k in SOURCE_FEATURES], dtype=np.float64)


# ARCOP policy regression target order
POLICY_INPUTS = [
    "risk", "ambiguity", "criticality", "creativity_demand",
    "evidence_coverage", "source_agreement", "model_confidence",
]
POLICY_OUTPUTS = [
    "grounding_intensity", "verification_depth", "creativity_allowance",
    "citation_requirement", "abstention_threshold", "escalation_threshold",
]
