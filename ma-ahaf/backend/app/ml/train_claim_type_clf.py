"""Claim-type classifier: TF-IDF + Logistic Regression (fast, CPU, no GPU).

Upgrade path: swap for a fine-tuned DistilBERT head (see `train_intent_clf.py`
for the transformers pattern). Classifies each atomic claim into
factual / numeric / causal / temporal / opinion / creative (proposal §7 agent 5).

    python -m app.ml.train_claim_type_clf
"""

from __future__ import annotations

import os

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from app.config import settings
from app.ml.synth_data import claim_type_dataset


def main() -> None:
    texts, labels = claim_type_dataset()
    Xtr, Xte, ytr, yte = train_test_split(texts, labels, test_size=0.2, random_state=0)
    pipe = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2)),
            ("clf", LogisticRegression(max_iter=1000, C=4.0)),
        ]
    )
    pipe.fit(Xtr, ytr)
    print(classification_report(yte, pipe.predict(Xte), zero_division=0))

    os.makedirs(settings.artifacts_dir, exist_ok=True)
    out = os.path.join(settings.artifacts_dir, "claim_type.joblib")
    joblib.dump(pipe, out)
    print(f"claim_type -> {out}")


if __name__ == "__main__":
    main()
