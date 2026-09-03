"""Agent 9 — Contradiction Agent (proposal §7).

Two jobs: (a) search retrieved evidence for passages that contradict a claim,
(b) check the answer for internal inconsistency between its own claims.
"""

from __future__ import annotations

from itertools import combinations

from app.agents.base import Agent
from app.config import settings
from app.nlp.nli import entail
from app.orchestration.state import RequestState

_INTERNAL_SYS = (
    "You are given a numbered list of CLAIMS from a single answer. Identify pairs "
    "of claims that directly contradict each other (cannot both be true). Reply "
    "ONLY JSON: {\"conflicts\": [[1, 3], [2, 5]]} using the claim numbers; empty "
    "list if there are no genuine contradictions."
)


class Contradiction(Agent):
    name = "contradiction"
    number = 9

    def _internal_conflicts_llm(self, state: RequestState, claims: list) -> list[tuple[str, str]]:
        """One LLM call to find contradicting claim pairs, instead of O(n^2) NLI calls."""
        body = "\n".join(f"{i + 1}. {c.text}" for i, c in enumerate(claims))
        data = state.gateway.complete_json(
            "verifier",
            [{"role": "system", "content": _INTERNAL_SYS}, {"role": "user", "content": body}],
            temperature=0.0, max_tokens=120,
        )
        out: list[tuple[str, str]] = []
        for pair in data.get("conflicts", []):
            try:
                i, j = int(pair[0]) - 1, int(pair[1]) - 1
            except (TypeError, ValueError, IndexError):
                continue
            if 0 <= i < len(claims) and 0 <= j < len(claims) and i != j:
                claims[i].contradiction_score = max(claims[i].contradiction_score, 0.6)
                claims[j].contradiction_score = max(claims[j].contradiction_score, 0.6)
                out.append((claims[i].text[:60], claims[j].text[:60]))
        return out

    def _run(self, state: RequestState):
        ev_by_id = {e.chunk_id: e for e in state.evidence}
        deep = state.policy.depth_bucket >= 1 if state.policy else True
        # when entailment scoring is done by the LLM (nli_backend=llm), agent 8 has
        # already run a strong contradiction pass on the same evidence — re-scanning
        # here would just repeat those calls, so skip the external re-scan.
        rescan_external = deep and settings.effective_nli_backend != "llm"
        external = 0
        for claim in state.claim_graph.claims:
            if claim.claim_type in ("creative", "opinion"):
                continue
            if not (rescan_external and (claim.contradiction_score > 0.2 or claim.criticality >= 0.6
                                         or claim.verdict != "supported")):
                continue
            worst = claim.contradiction_score
            for cid in claim.evidence_ids[:3]:
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

        # internal consistency — bounded, deep depth only
        internal_conflicts: list[tuple[str, str]] = []
        if deep:
            claims = [c for c in state.claim_graph.claims if c.claim_type != "creative"][:8]
            if len(claims) >= 2:
                if settings.effective_nli_backend == "llm" and state.gateway is not None:
                    # single batched LLM call instead of O(n^2) pairwise NLI
                    internal_conflicts = self._internal_conflicts_llm(state, claims)
                else:
                    for a, b in combinations(claims[:6], 2):
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
