from __future__ import annotations

from app.eval.metrics import reliability_index, unsupported_claim_rate
from app.eval.pareto import dominates, frontier_gain, pareto_front


def test_unsupported_rate():
    claims = [
        {"claim_type": "factual", "verdict": "supported"},
        {"claim_type": "factual", "verdict": "insufficient"},
        {"claim_type": "creative", "verdict": "unverified"},
    ]
    assert unsupported_claim_rate(claims) == 0.5


def test_reliability_index_bounds():
    assert 0 <= reliability_index({"unsupported_rate": 0.1, "citation_precision": 0.9,
                                   "entailment": 0.8, "ece": 0.05}) <= 1


def test_pareto_front_and_dominance():
    pts = [
        {"creativity": 0.2, "reliability": 0.9},
        {"creativity": 0.5, "reliability": 0.8},
        {"creativity": 0.4, "reliability": 0.5},
    ]
    front = pareto_front(pts)
    assert {"creativity": 0.4, "reliability": 0.5} not in front
    assert dominates({"creativity": 0.6, "reliability": 0.9},
                     {"creativity": 0.4, "reliability": 0.5})
    assert frontier_gain([{"creativity": 0.9, "reliability": 0.9}],
                         [{"creativity": 0.5, "reliability": 0.5}]) == 1.0
