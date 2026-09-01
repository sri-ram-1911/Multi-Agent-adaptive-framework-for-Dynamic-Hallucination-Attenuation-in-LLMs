"""Hallucination budget (proposal §5) — a context-specific tolerance for
unsupported claims. High-stakes tasks get a near-zero budget; ideation tasks a
bounded creative latitude.
"""

from __future__ import annotations

from app.claimgraph.schema import ClaimGraph

# max tolerated sum of (risk * criticality) over claims, by task type
_BUDGET = {
    "high_stakes": 0.05,
    "factual": 0.20,
    "analytical": 0.35,
    "mixed": 0.50,
    "creative": 0.85,
}


def budget_for(task_type: str, *, criticality: float) -> float:
    base = _BUDGET.get(task_type, 0.25)
    return max(0.02, base - 0.15 * max(0.0, criticality - 0.5) * 2)


def consumed(cg: ClaimGraph) -> float:
    return sum(c.risk_score * c.criticality for c in cg.claims)


def over_budget(cg: ClaimGraph, task_type: str, criticality: float) -> tuple[bool, float, float]:
    b = budget_for(task_type, criticality=criticality)
    used = consumed(cg)
    return used > b, used, b
