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

# high-consequence cues: a hit here forces the high_stakes route regardless of
# what the (small) zero-shot model says — medical / legal / financial / safety.
_HIGH_STAKES_CUES = (
    "dose", "dosage", "mg/kg", "ibuprofen", "acetaminophen", "paracetamol",
    "medication", "prescri", "diagnos", "symptom", "overdose", "allerg",
    "lawsuit", "legal advice", "contract clause", "liable", "liability",
    "invest", "portfolio", "tax owed", "which stock", "safe daily", "safe dose",
    "toxic", "poison", "self-harm", "seizure", "blood pressure",
)


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

        # safety override: never let a borderline classifier downgrade a
        # high-consequence request out of the deep-verification / low-budget path.
        low = text.lower()
        if task_type != "high_stakes" and any(cue in low for cue in _HIGH_STAKES_CUES):
            scores = {**scores, "high_stakes": max(scores.values(), default=0.5) + 0.05}
            task_type = "high_stakes"

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
