"""Zero-shot text classification (DL) — facebook/bart-large-mnli.

Used by the Intent & Task Classifier when no fine-tuned head is present. Offline
fallback: keyword scoring.
"""

from __future__ import annotations

import threading

from app.config import settings
from app.core.logging import get_logger

log = get_logger("nlp.zeroshot")
_lock = threading.Lock()
_pipe = None
_offline = settings.llm.provider == "mock"

_KEYWORDS = {
    "factual": ["what", "when", "who", "define", "fact", "how many"],
    "analytical": ["why", "compare", "analyse", "analyze", "evaluate", "trade-off", "reason"],
    "creative": ["write", "story", "poem", "imagine", "invent", "brainstorm", "slogan", "design"],
    "mixed": ["summarise and", "explain and", "and suggest", "and pitch", "and write"],
    "high_stakes": ["dose", "legal", "contract", "diagnos", "invest", "regulat", "safe", "compliance"],
}


def _load():
    global _pipe
    if _pipe is not None or _offline:
        return _pipe
    with _lock:
        if _pipe is None:
            from transformers import pipeline

            log.info("zeroshot.loading", model=settings.zeroshot_model)
            _pipe = pipeline("zero-shot-classification", model=settings.zeroshot_model)
    return _pipe


def classify(text: str, labels: list[str], *, multi_label: bool = False) -> dict[str, float]:
    if _offline or _load() is None:
        t = text.lower()
        raw = {lab: sum(t.count(k) for k in _KEYWORDS.get(lab, [lab])) + 0.01 for lab in labels}
        z = sum(raw.values())
        return {k: v / z for k, v in raw.items()}
    out = _load()(text, labels, multi_label=multi_label)
    return dict(zip(out["labels"], out["scores"], strict=True))
