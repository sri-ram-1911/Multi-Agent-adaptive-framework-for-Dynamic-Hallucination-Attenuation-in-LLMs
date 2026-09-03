"""Natural Language Inference for claim<->evidence entailment & contradiction.

Two backends (``settings.effective_nli_backend``):
- ``local``  DeBERTa-v3-base-mnli-fever-anli via transformers (CPU).
- ``llm``    the gateway verifier model scores a claim against several passages
             in one batched call — no local model, fast with a hosted provider.

Offline (``provider == mock``) always uses a lexical-overlap + negation heuristic.
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

# a per-request Gateway can be attached so LLM-backed NLI shares the usage meter
_gateway = None


def set_gateway(gw) -> None:  # noqa: ANN001
    global _gateway
    _gateway = gw


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
    neg = len((ps | hs) & _NEG) % 2
    if neg and overlap > 0.3:
        return {"entailment": 0.1, "neutral": 0.2, "contradiction": 0.7}
    if overlap > 0.45:
        return {"entailment": 0.7, "neutral": 0.25, "contradiction": 0.05}
    return {"entailment": 0.15, "neutral": 0.75, "contradiction": 0.10}


def entail(premise: str, hypothesis: str) -> dict[str, float]:
    """P over {entailment, neutral, contradiction} that *premise* implies *hypothesis*."""
    if _offline:
        return _heuristic(premise, hypothesis)
    if settings.effective_nli_backend == "llm" and _gateway is not None:
        return _llm_batch(hypothesis, [premise])[0]
    pipe = _load()
    out = pipe({"text": premise, "text_pair": hypothesis})
    scores = {d["label"].lower(): float(d["score"]) for d in out}
    return {
        "entailment": scores.get("entailment", 0.0),
        "neutral": scores.get("neutral", 0.0),
        "contradiction": scores.get("contradiction", 0.0),
    }


_LLM_SYS = (
    "You are a natural-language-inference judge. For each numbered PASSAGE decide "
    "its relationship to the CLAIM: 'entailment' (passage supports the claim), "
    "'contradiction' (passage refutes it), or 'neutral' (neither). "
    "Reply ONLY JSON: {\"results\":[{\"i\":1,\"label\":\"entailment|neutral|contradiction\","
    "\"p\":0.0-1.0}, ...]}"
)


def _llm_batch(claim: str, passages: list[str]) -> list[dict[str, float]]:
    if _gateway is None:
        return [_heuristic(p, claim) for p in passages]
    body = f"CLAIM: {claim}\n\n" + "\n".join(
        f"PASSAGE {i + 1}: {p[:600]}" for i, p in enumerate(passages)
    )
    data = _gateway.complete_json(
        "verifier",
        [{"role": "system", "content": _LLM_SYS}, {"role": "user", "content": body}],
        temperature=0.0, max_tokens=350,
    )
    out: list[dict[str, float]] = [{"entailment": 0.15, "neutral": 0.7, "contradiction": 0.15}
                                   for _ in passages]
    for r in data.get("results", []):
        try:
            idx = int(r["i"]) - 1
            label = str(r["label"]).lower()
            p = min(0.99, max(0.34, float(r.get("p", 0.7))))
        except (KeyError, ValueError, TypeError):
            continue
        if not (0 <= idx < len(out) and label in ("entailment", "neutral", "contradiction")):
            continue
        rest = round(1.0 - p, 4)
        if label == "entailment":
            # a confident entailment implies the passage does NOT contradict
            out[idx] = {"entailment": p, "neutral": rest * 0.85, "contradiction": rest * 0.15}
        elif label == "contradiction":
            out[idx] = {"contradiction": p, "neutral": rest * 0.85, "entailment": rest * 0.15}
        else:
            out[idx] = {"neutral": p, "entailment": rest / 2, "contradiction": rest / 2}
    return out


def best_support(claim: str, passages: list[str], *, max_passages: int = 4) -> tuple[float, float, int]:
    """Return (max_entailment, max_contradiction, best_passage_idx) over passages."""
    ps = passages[:max_passages]
    if not ps:
        return 0.0, 0.0, -1
    if _offline:
        results = [_heuristic(p, claim) for p in ps]
    elif settings.effective_nli_backend == "llm" and _gateway is not None:
        results = _llm_batch(claim, ps)
    else:
        pipe = _load()
        results = []
        for p in ps:
            o = pipe({"text": p, "text_pair": claim})
            sc = {d["label"].lower(): float(d["score"]) for d in o}
            results.append({"entailment": sc.get("entailment", 0.0),
                            "neutral": sc.get("neutral", 0.0),
                            "contradiction": sc.get("contradiction", 0.0)})
    best_e, best_c, best_i = 0.0, 0.0, -1
    for i, r in enumerate(results):
        if r["entailment"] > best_e:
            best_e, best_i = r["entailment"], i
        best_c = max(best_c, r["contradiction"])
    return best_e, best_c, best_i
