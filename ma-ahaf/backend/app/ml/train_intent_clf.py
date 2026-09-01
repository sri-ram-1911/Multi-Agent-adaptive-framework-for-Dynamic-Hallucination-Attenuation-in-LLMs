"""Optional: fine-tune DistilBERT for the intent/task classifier (proposal §7 agent 1).

Runtime default is zero-shot NLI (`app/nlp/zeroshot.py`); this script produces a
faster, cheaper fine-tuned head when labelled prompts are available. Requires
`transformers[torch]`. Skipped by `bootstrap_models` unless `--with-intent`.

    python -m app.ml.train_intent_clf
"""

from __future__ import annotations

import os

from app.config import settings
from app.core.logging import get_logger

log = get_logger("ml.intent")
LABELS = ["factual", "analytical", "creative", "mixed", "high_stakes"]


def main() -> None:  # pragma: no cover - heavy, opt-in
    try:
        import numpy as np
        from datasets import Dataset
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
            Trainer,
            TrainingArguments,
        )
    except ImportError:
        log.warning("intent.deps_missing", hint="pip install 'transformers[torch]' datasets")
        return

    from app.ml.synth_data import rng

    # crude synthetic prompt set; replace with client-labelled prompts
    seeds = {
        "factual": ["What is the boiling point of water?", "When did WW2 end?"],
        "analytical": ["Compare REST and GraphQL for our use case.", "Why did revenue drop?"],
        "creative": ["Write a haiku about winter.", "Invent a mascot for a coffee brand."],
        "mixed": ["Summarise the report and suggest a catchy title.",
                  "Explain the metric and pitch a dashboard concept."],
        "high_stakes": ["What dose of warfarin is safe?", "Is this contract clause enforceable?"],
    }
    texts, labels = [], []
    for _ in range(1500):
        li = int(rng.integers(len(LABELS)))
        base = seeds[LABELS[li]]
        texts.append(base[int(rng.integers(len(base)))])
        labels.append(li)

    tok = AutoTokenizer.from_pretrained("distilbert-base-uncased")
    ds = Dataset.from_dict({"text": texts, "label": labels}).train_test_split(test_size=0.2)
    ds = ds.map(lambda b: tok(b["text"], truncation=True, padding="max_length", max_length=64),
                batched=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        "distilbert-base-uncased", num_labels=len(LABELS)
    )
    out_dir = os.path.join(settings.artifacts_dir, "intent")
    args = TrainingArguments(output_dir=out_dir, num_train_epochs=2, per_device_train_batch_size=16,
                             eval_strategy="epoch", logging_steps=50, report_to=[])

    def metrics(p):
        preds = np.argmax(p.predictions, axis=1)
        return {"acc": float((preds == p.label_ids).mean())}

    Trainer(model=model, args=args, train_dataset=ds["train"], eval_dataset=ds["test"],
            compute_metrics=metrics).train()
    model.save_pretrained(out_dir)
    tok.save_pretrained(out_dir)
    print(f"intent classifier -> {out_dir}")


if __name__ == "__main__":
    main()
