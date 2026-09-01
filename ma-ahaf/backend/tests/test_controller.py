from __future__ import annotations

from app.claimgraph.schema import Claim
from app.controller import budget, calibration
from app.controller.arcop import Signals, policy
from app.controller.consensus import claim_disagreement
from app.controller.risk_model import score_claim


def test_high_stakes_policy_is_strict():
    p = policy(Signals(risk=0.9, task_type="high_stakes", criticality=0.95))
    assert p.verification_depth > 0.6
    assert p.citation_requirement > 0.6
    assert p.creativity_allowance < 0.3


def test_creative_policy_is_loose():
    p = policy(Signals(risk=0.1, task_type="creative", criticality=0.1))
    assert p.creativity_allowance > 0.6
    assert p.verification_depth < 0.5


def test_risk_model_monotonic_in_missing_evidence():
    low = score_claim(Claim(id="a", ordinal=0, text="x", evidence_coverage=0.9, criticality=0.8))
    high = score_claim(Claim(id="b", ordinal=1, text="x", evidence_coverage=0.0, criticality=0.8,
                             contradiction_score=0.7))
    assert high.risk_score > low.risk_score
    assert set(high.risk_contributions) >= {"missing_evidence", "contradiction"}


def test_calibration_shrinks_overconfidence():
    assert calibration.calibrate(0.95) < 0.95
    assert calibration.ece([0.9, 0.9], [1, 0]) > 0


def test_consensus_disagreement():
    assert claim_disagreement(["supported", "refuted"]) == 0.5
    assert claim_disagreement(["supported", "supported", "supported"]) == 0.0


def test_budget_high_stakes_is_tight():
    assert budget.budget_for("high_stakes", criticality=0.9) < budget.budget_for("creative", criticality=0.2)
