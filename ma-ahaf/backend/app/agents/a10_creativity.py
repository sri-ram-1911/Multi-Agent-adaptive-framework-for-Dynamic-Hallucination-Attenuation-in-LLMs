"""Agent 10 — Creativity Agent (proposal §7).

Assesses novelty / diversity and whether creative intent is preserved. DL/ML:
embedding-based novelty vs the KB centroid + lexical diversity (distinct-n,
self-BLEU across candidates).
"""

from __future__ import annotations

import numpy as np

from app.agents.base import Agent
from app.orchestration.state import RequestState
from app.retrieval.embeddings import embed


def _distinct_n(text: str, n: int) -> float:
    toks = text.lower().split()
    if len(toks) < n:
        return 0.0
    grams = list(zip(*[toks[i:] for i in range(n)], strict=False))
    return len(set(grams)) / max(1, len(grams))


def _self_bleu(cands: list[str]) -> float:
    if len(cands) < 2:
        return 0.0
    try:
        from sacrebleu import sentence_bleu

        scores = []
        for i, c in enumerate(cands):
            refs = [cands[j] for j in range(len(cands)) if j != i]
            scores.append(sentence_bleu(c, refs).score / 100)
        return float(np.mean(scores))
    except Exception:  # pragma: no cover
        return 0.0


class Creativity(Agent):
    name = "creativity"
    number = 10

    def _run(self, state: RequestState):
        draft = state.chosen_candidate
        d1, d2 = _distinct_n(draft, 1), _distinct_n(draft, 2)
        self_bleu = _self_bleu(state.candidates)          # lower = more diverse
        diversity = float(np.clip(1.0 - self_bleu, 0, 1))

        # novelty: distance of the draft from the retrieved-evidence centroid
        novelty = 0.5
        if state.evidence:
            vecs = np.asarray(embed([e.text for e in state.evidence[:8]]))
            centroid = vecs.mean(axis=0)
            dv = np.asarray(embed([draft])[0])
            cos = float(dv @ centroid / ((np.linalg.norm(dv) * np.linalg.norm(centroid)) or 1))
            novelty = float(np.clip(1.0 - cos, 0, 1))

        creativity_score = round(0.35 * d2 + 0.25 * diversity + 0.40 * novelty, 3)

        # locate explicitly creative spans (claims typed 'creative')
        spans = [c.span for c in state.claim_graph.claims if c.claim_type == "creative" and c.span]
        state.creativity_score = creativity_score
        state.creative_spans = spans

        preserved = (
            creativity_score >= 0.4 * state.policy.creativity_allowance
            if state.policy.creativity_allowance > 0.3 else True
        )
        return (
            {"creativity_score": creativity_score, "distinct_1": round(d1, 3),
             "distinct_2": round(d2, 3), "self_bleu": round(self_bleu, 3),
             "novelty": round(novelty, 3), "creative_spans": len(spans),
             "intent_preserved": preserved},
            f"creativity={creativity_score:.2f} (novelty {novelty:.2f}, diversity {diversity:.2f})",
            "creativity/embed+distinct-n",
        )
