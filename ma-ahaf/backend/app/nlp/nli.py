"""Natural Language Inference (DL) for claim<->evidence entailment & contradiction.

Model: MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli (labels: entailment,
neutral, contradiction). Offline fallback: lexical-overlap + negation heuristic.
"""

from __future__ import annotations

import threading

from app.config import settings
from app.core.logging import get_logger

log = get_logger("nlp.nli")
_lock = threading.Lock()
_pipe = None
_offline = settings.llm.provider == "mock"
_NEG = {"not", "no", "never", "cannot", "n't", "false", "incorrect", "unsupported"}


def _load():
    global _pipe
    if _pipe is not None or _offline:
        return _pipe
    with _lock:
        if _pipe is None:
            from transformers import pipeline

            log.info("nli.loading", model=settings.nli_model)
            _pipe = pipeline("text-classification", model=settings.nli_model,
                             top_k=None, truncation=True)
    return _pipe


def _heuristic(premise: str, hypothesis: str) -> dict[str, float]:
    ps, hs = set(premise.lower().split()), set(hypothesis.lower().split())
    overlap = len(ps & hs) / (len(hs) or 1)
    neg = len((ps | hs) & _NEG) % 2  # odd number of negations -> polarity flip
    if neg and overlap > 0.3:
        return {"entailment": 0.1, "neutral": 0.2, "contradiction": 0.7}
    if overlap > 0.45:
        return {"entailment": 0.7, "neutral": 0.25, "contradiction": 0.05}
    return {"entailment": 0.15, "neutral": 0.75, "contradiction": 0.10}


def entail(premise: str, hypothesis: str) -> dict[str, float]:
    """P over {entailment, neutral, contradiction} that *premise* implies *hypothesis*."""
    if _offline:
        return _heuristic(premise, hypothesis)
    pipe = _load()
    out = pipe({"text": premise, "text_pair": hypothesis})
    scores = {d["label"].lower(): float(d["score"]) for d in out}
    return {
        "entailment": scores.get("entailment", 0.0),
        "neutral": scores.get("neutral", 0.0),
        "contradiction": scores.get("contradiction", 0.0),
    }


def best_support(claim: str, passages: list[str]) -> tuple[float, float, int]:
    """Return (max_entailment, max_contradiction, best_passage_idx) over passages."""
    best_e, best_c, best_i = 0.0, 0.0, -1
    for i, p in enumerate(passages):
        r = entail(p, claim)
        if r["entailment"] > best_e:
            best_e, best_i = r["entailment"], i
        best_c = max(best_c, r["contradiction"])
    return best_e, best_c, best_i
