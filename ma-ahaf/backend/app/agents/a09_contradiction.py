"""Agent 9 — Contradiction Agent (proposal §7).

Two jobs: (a) search retrieved evidence for passages that contradict a claim,
(b) check the answer for internal inconsistency between its own claims.
"""

from __future__ import annotations

from itertools import combinations

from app.agents.base import Agent
from app.nlp.nli import entail
from app.orchestration.state import RequestState


class Contradiction(Agent):
    name = "contradiction"
    number = 9

    def _run(self, state: RequestState):
        ev_by_id = {e.chunk_id: e for e in state.evidence}
        external = 0
        for claim in state.claim_graph.claims:
            if claim.claim_type in ("creative", "opinion"):
                continue
            worst = claim.contradiction_score
            for cid in claim.evidence_ids:
                ev = ev_by_id.get(cid)
                if not ev:
                    continue
                r = entail(ev.text, claim.text)
                if r["contradiction"] > worst:
                    worst = r["contradiction"]
                    ev.stance = "contradict"
            if worst > claim.contradiction_score:
                external += 1
            claim.contradiction_score = round(worst, 3)

        # internal consistency
        internal_conflicts: list[tuple[str, str]] = []
        claims = [c for c in state.claim_graph.claims if c.claim_type != "creative"]
        for a, b in combinations(claims, 2):
            r = entail(a.text, b.text)
            if r["contradiction"] > 0.6:
                internal_conflicts.append((a.text[:60], b.text[:60]))
                a.contradiction_score = max(a.contradiction_score, 0.6)
                b.contradiction_score = max(b.contradiction_score, 0.6)

        return (
            {"external_contradictions": external,
             "internal_conflicts": internal_conflicts,
             "contradicting_passages": [e.chunk_id for e in state.evidence if e.stance == "contradict"]},
            f"{external} claims with contradicting evidence; "
            f"{len(internal_conflicts)} internal conflicts",
            "nli-contradiction/v1",
        )
