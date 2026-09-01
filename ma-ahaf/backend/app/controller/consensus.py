"""Consensus engine / conflict resolver (proposal §7 'Resolution').

Aggregates per-claim verdicts from independent verification passes, quantifies
disagreement, and turns disagreement into a routing signal (proposal §5
'Disagreement-Driven Escalation').
"""

from __future__ import annotations

from collections import Counter

from app.claimgraph.schema import Claim

_VERDICT_SCORE = {"supported": 1.0, "insufficient": 0.4, "refuted": 0.0, "unverified": 0.5}


def claim_disagreement(verdicts: list[str]) -> float:
    """Normalised entropy-ish spread of verdicts in [0,1]."""
    if len(verdicts) < 2:
        return 0.0
    counts = Counter(verdicts)
    top = counts.most_common(1)[0][1]
    return 1.0 - top / len(verdicts)


def resolve_claim(claim: Claim, verdicts: list[str], entail_scores: list[float]) -> Claim:
    dis = claim_disagreement(verdicts)
    claim.agent_disagreement = dis
    # weighted vote: entailment-weighted verdict score
    if verdicts:
        num = sum(_VERDICT_SCORE[v] * (0.5 + e) for v, e in zip(verdicts, entail_scores, strict=False))
        den = sum(0.5 + e for e in entail_scores) or len(verdicts)
        agg = num / den
    else:
        agg = 0.5
    claim.verdict = (
        "supported" if agg >= 0.66 else "refuted" if agg <= 0.25 else "insufficient"
    )
    return claim


def request_disagreement(claims: list[Claim]) -> float:
    if not claims:
        return 0.0
    return sum(c.agent_disagreement for c in claims) / len(claims)
