"""Download HF models into the cache + train the sklearn artifacts.

    python -m scripts.bootstrap_models [--with-intent]
"""

from __future__ import annotations

import sys

from app.config import settings
from app.core.logging import get_logger
from app.ml import registry
from app.ml.train_claim_type_clf import main as train_claim_type
from app.ml.train_policy import main as train_policy
from app.ml.train_risk_model import main as train_risk
from app.ml.train_source_quality import main as train_source

log = get_logger("bootstrap")


def _download_hf() -> None:
    if settings.llm.provider == "mock":
        log.info("bootstrap.offline_skip_hf")
        return
    from sentence_transformers import CrossEncoder, SentenceTransformer
    from transformers import pipeline

    log.info("bootstrap.embeddings", model=settings.embedding_model)
    SentenceTransformer(settings.embedding_model)
    log.info("bootstrap.reranker", model=settings.reranker_model)
    CrossEncoder(settings.reranker_model)
    log.info("bootstrap.nli", model=settings.nli_model)
    pipeline("text-classification", model=settings.nli_model, top_k=None)
    log.info("bootstrap.zeroshot", model=settings.zeroshot_model)
    pipeline("zero-shot-classification", model=settings.zeroshot_model)


def _train_calibrator() -> None:
    import joblib
    from sklearn.isotonic import IsotonicRegression

    from app.ml.synth_data import calibration_dataset

    raw, y = calibration_dataset()
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(raw, y)
    joblib.dump(iso, f"{settings.artifacts_dir}/calibrator.joblib")
    log.info("bootstrap.calibrator_trained")


def main() -> None:
    _download_hf()
    train_risk()
    train_claim_type()
    train_source()
    train_policy()
    _train_calibrator()
    if "--with-intent" in sys.argv:
        from app.ml.train_intent_clf import main as train_intent

        train_intent()
    registry.clear()
    log.info("bootstrap.done")


if __name__ == "__main__":
    main()
