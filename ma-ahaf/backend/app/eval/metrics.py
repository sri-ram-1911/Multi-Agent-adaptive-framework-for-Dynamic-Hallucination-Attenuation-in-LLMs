"""Evaluation metrics (proposal §4, §15).

reliability side: unsupported-claim rate, citation precision/recall, entailment
accuracy, calibration (ECE / Brier).
creativity side: distinct-2, self-BLEU (diversity), novelty.
cost side: latency, tokens, USD.
"""

from __future__ import annotations

import numpy as np

from app.agents.a10_creativity import _distinct_n
from app.controller.calibration import ece
from app.nlp.nli import entail


def unsupported_claim_rate(claims: list[dict]) -> float:
    checkable = [c for c in claims if c.get("claim_type") not in ("creative", "opinion")]
    if not checkable:
        return 0.0
    bad = sum(1 for c in checkable if c.get("verdict") in ("refuted", "insufficient", "unverified"))
    return bad / len(checkable)


def citation_pr(claims: list[dict], gold_evidence: list[str]) -> tuple[float, float]:
    """Approximate: a claim is 'correctly cited' if any of its evidence entails it
    AND overlaps a gold passage. Precision over cited claims, recall over factual claims."""
    factual = [c for c in claims if c.get("claim_type") not in ("creative", "opinion")]
    if not factual:
        return 1.0, 1.0
    cited = [c for c in factual if c.get("evidence")]
    gold_text = " ".join(gold_evidence).lower()

    def ok(c: dict) -> bool:
        if not gold_evidence:
            return c.get("verdict") == "supported"
        supported = c.get("verdict") == "supported"
        overlaps = any(w in gold_text for w in c["text"].lower().split() if len(w) > 5)
        return supported and overlaps

    precision = (sum(ok(c) for c in cited) / len(cited)) if cited else 0.0
    recall = sum(ok(c) for c in factual) / len(factual)
    return precision, recall


def entailment_accuracy(response: str, reference: str) -> float:
    if not reference:
        return float("nan")
    return entail(reference, response)["entailment"]


def creativity_scores(response: str, candidates: list[str] | None = None) -> dict[str, float]:
    d2 = _distinct_n(response, 2)
    self_bleu = 0.0
    if candidates and len(candidates) > 1:
        try:
            from sacrebleu import sentence_bleu

            self_bleu = float(np.mean([
                sentence_bleu(c, [x for j, x in enumerate(candidates) if j != i]).score / 100
                for i, c in enumerate(candidates)
            ]))
        except Exception:
            pass
    return {"distinct_2": round(d2, 3), "self_bleu": round(self_bleu, 3),
            "diversity": round(1 - self_bleu, 3)}


def calibration_metrics(confidences: list[float], correct: list[int]) -> dict[str, float]:
    if not confidences:
        return {"ece": 0.0, "brier": 0.0}
    c = np.asarray(confidences)
    y = np.asarray(correct)
    return {"ece": round(ece(list(c), list(y)), 4),
            "brier": round(float(np.mean((c - y) ** 2)), 4)}


def reliability_index(row_metrics: dict) -> float:
    """Aggregate reliability score in [0,1] for the Pareto frontier."""
    return float(np.clip(
        0.45 * (1 - row_metrics.get("unsupported_rate", 0))
        + 0.25 * row_metrics.get("citation_precision", 0)
        + 0.20 * row_metrics.get("entailment", 0)
        + 0.10 * (1 - row_metrics.get("ece", 0)),
        0, 1,
    ))
