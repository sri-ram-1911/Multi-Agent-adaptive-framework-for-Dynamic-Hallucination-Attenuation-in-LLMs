"""Agent 8 — Verification Agent (proposal §7).

Tests claim<->evidence entailment with the NLI model (DL). For deep verification
depth it also asks an independent LLM verifier (different role/model family) for a
second opinion, and — for critical claims — runs a counterfactual probe ("what
evidence would falsify this?").
"""

from __future__ import annotations

from app.agents.base import Agent
from app.config import settings
from app.controller.consensus import resolve_claim
from app.nlp.nli import best_support
from app.orchestration.state import RequestState

_VERIFY_SYS = (
    "You are an independent verifier. Given a CLAIM and EVIDENCE passages, reply "
    "JSON {\"verdict\": supported|refuted|insufficient, \"rationale\": str}. "
    "Judge only from the evidence provided."
)
_COUNTERFACTUAL_SYS = (
    "State in one sentence what specific evidence would falsify or seriously weaken "
    "this claim. Then say whether the provided evidence contains any such signal "
    "(JSON {\"falsifier\": str, \"present\": bool})."
)


class Verification(Agent):
    name = "verification"
    number = 8

    def _run(self, state: RequestState):
        depth = state.policy.depth_bucket  # 0 light, 1 std, 2 deep
        ev_by_id = {e.chunk_id: e for e in state.evidence}
        verified = 0

        for claim in state.claim_graph.claims:
            if claim.claim_type in ("creative", "opinion"):
                claim.verdict = "unverified"
                claim.evidence_coverage = 1.0
                continue

            passages = [ev_by_id[cid].text for cid in claim.evidence_ids if cid in ev_by_id]
            verdicts: list[str] = []
            entail_scores: list[float] = []

            if passages:
                e_score, c_score, best_i = best_support(claim.text, passages)
                claim.entailment_score = round(e_score, 3)
                claim.contradiction_score = round(c_score, 3)
                claim.evidence_coverage = round(min(1.0, len(passages) / settings.rerank_k), 3)
                nli_verdict = (
                    "supported" if e_score >= 0.6 and c_score < 0.4
                    else "refuted" if c_score >= 0.55
                    else "insufficient"
                )
                verdicts.append(nli_verdict)
                entail_scores.append(e_score)
                if best_i >= 0 and best_i < len(claim.evidence_ids):
                    ev_by_id[claim.evidence_ids[best_i]].stance = "support"
            else:
                claim.evidence_coverage = 0.0
                verdicts.append("insufficient")
                entail_scores.append(0.0)

            # independent LLM verifier for standard+ depth or critical claims
            if passages and (depth >= 1 or claim.criticality >= 0.7):
                data = state.gateway.complete_json(
                    "verifier",
                    [
                        {"role": "system", "content": _VERIFY_SYS},
                        {"role": "user",
                         "content": f"CLAIM: {claim.text}\n\nEVIDENCE:\n" +
                                    "\n---\n".join(p[:500] for p in passages[:4])},
                    ],
                    temperature=0.0, max_tokens=250,
                )
                v = str(data.get("verdict", "insufficient")).lower()
                if v in ("supported", "refuted", "insufficient"):
                    verdicts.append(v)
                    entail_scores.append(0.7 if v == "supported" else 0.2)

            # counterfactual probe for deep depth on critical claims
            if depth >= 2 and claim.criticality >= 0.6 and passages:
                cf = state.gateway.complete_json(
                    "verifier",
                    [
                        {"role": "system", "content": _COUNTERFACTUAL_SYS},
                        {"role": "user",
                         "content": f"CLAIM: {claim.text}\nEVIDENCE:\n" +
                                    "\n".join(p[:400] for p in passages[:3])},
                    ],
                    temperature=0.0, max_tokens=180,
                )
                if cf.get("present"):
                    verdicts.append("refuted")
                    entail_scores.append(0.1)
                    claim.risk_contributions["counterfactual"] = 1.0

            resolve_claim(claim, verdicts, entail_scores)
            claim.source_agreement = state.signals.source_agreement
            claim.model_uncertainty = round(1.0 - state.signals.model_confidence, 3)
            verified += 1

        return (
            {"verified": verified, "depth": depth,
             "verdicts": {c.text[:60]: c.verdict for c in state.claim_graph.claims}},
            f"verified {verified} claims at depth {depth}",
            f"{settings.nli_model} + {state.gateway.model_for('verifier')}",
        )
