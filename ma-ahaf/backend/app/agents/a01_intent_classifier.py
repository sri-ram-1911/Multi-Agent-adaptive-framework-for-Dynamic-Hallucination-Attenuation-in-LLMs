"""Agent 1 — Intent & Task Classifier (proposal §7).

Classifies the request as factual / analytical / creative / mixed / high_stakes
and estimates ambiguity. DL: zero-shot NLI (bart-large-mnli) or a fine-tuned
DistilBERT head if present.
"""

from __future__ import annotations

import os

from app.agents.base import Agent
from app.config import settings
from app.nlp.zeroshot import classify
from app.orchestration.state import RequestState

LABELS = ["factual", "analytical", "creative", "mixed", "high_stakes"]
_HEDGES = ("maybe", "not sure", "somehow", "something", "etc", "or so", "kind of")


def _finetuned_predict(text: str) -> dict[str, float] | None:
    path = os.path.join(settings.artifacts_dir, "intent")
    if not os.path.isdir(path):
        return None
    try:  # pragma: no cover - opt-in heavy path
        from transformers import pipeline

        pipe = pipeline("text-classification", model=path, top_k=None)
        return {d["label"].lower(): float(d["score"]) for d in pipe(text)}
    except Exception:
        return None


class IntentClassifier(Agent):
    name = "intent_classifier"
    number = 1

    def _run(self, state: RequestState):
        text = state.prompt if not state.context else f"{state.prompt}\n\ncontext: {state.context}"
        ft = _finetuned_predict(text)
        scores = ft or classify(text, LABELS)
        task_type = max(scores, key=scores.get)

        words = text.split()
        ambiguity = min(
            1.0,
            0.15
            + 0.4 * sum(h in text.lower() for h in _HEDGES) / max(1, len(_HEDGES))
            + (0.3 if len(words) < 6 else 0.0)
            + (0.2 if "?" not in text and task_type != "creative" else 0.0),
        )

        state.task_type = task_type
        state.ambiguity = round(ambiguity, 3)
        model_v = "distilbert-intent-head" if ft else settings.zeroshot_model
        return (
            {"task_type": task_type, "ambiguity": state.ambiguity,
             "scores": {k: round(v, 3) for k, v in scores.items()}},
            f"task={task_type}, ambiguity={state.ambiguity:.2f}",
            model_v,
        )
