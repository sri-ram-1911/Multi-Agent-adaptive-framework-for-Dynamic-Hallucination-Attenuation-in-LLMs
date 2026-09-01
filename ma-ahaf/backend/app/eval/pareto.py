"""Reliability-Creativity Pareto frontier (proposal §5, §15)."""

from __future__ import annotations


def pareto_front(points: list[dict], x: str = "creativity", y: str = "reliability") -> list[dict]:
    """Return the non-dominated points (maximising both x and y)."""
    pts = sorted(points, key=lambda p: (-p[x], -p[y]))
    front, best_y = [], -1.0
    for p in pts:
        if p[y] > best_y:
            front.append(p)
            best_y = p[y]
    return front


def dominates(a: dict, b: dict, keys=("creativity", "reliability")) -> bool:
    return all(a[k] >= b[k] for k in keys) and any(a[k] > b[k] for k in keys)


def frontier_gain(system_points: list[dict], baseline_points: list[dict]) -> float:
    """Fraction of baseline points the system Pareto-dominates."""
    if not baseline_points:
        return 0.0
    dominated = sum(
        1 for b in baseline_points if any(dominates(s, b) for s in system_points)
    )
    return round(dominated / len(baseline_points), 3)
