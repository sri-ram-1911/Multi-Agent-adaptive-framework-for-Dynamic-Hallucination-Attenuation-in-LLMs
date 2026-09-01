"""Train the claim-level hallucination risk model H(x) (proposal §9).

Logistic regression over the 7 risk signals -> P(claim unsupported). Coefficients
are the learned w1..w7; per-claim `contributions` (coef * feature) provide the
'explain why this claim was high risk' capability required by §9.

    python -m app.ml.train_risk_model
"""

from __future__ import annotations

import os

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split

from app.config import settings
from app.ml.features import RISK_FEATURES
from app.ml.synth_data import risk_dataset


def main() -> None:
    X, y = risk_dataset()
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=0)

    base = LogisticRegression(max_iter=1000, C=1.0)
    base.fit(Xtr, ytr)
    clf = CalibratedClassifierCV(base, method="isotonic", cv=3)
    clf.fit(Xtr, ytr)

    proba = clf.predict_proba(Xte)[:, 1]
    auc = roc_auc_score(yte, proba)
    brier = brier_score_loss(yte, proba)
    coefs = dict(zip(RISK_FEATURES, base.coef_[0].round(3).tolist(), strict=True))

    os.makedirs(settings.artifacts_dir, exist_ok=True)
    out = os.path.join(settings.artifacts_dir, "risk_model.joblib")
    joblib.dump(
        {"model": clf, "linear": base, "features": RISK_FEATURES,
         "coef": coefs, "intercept": float(base.intercept_[0]),
         "metrics": {"auc": round(auc, 4), "brier": round(brier, 4)}},
        out,
    )
    print(f"risk_model -> {out}")
    print(f"  AUC={auc:.3f}  Brier={brier:.3f}")
    print(f"  learned weights: {coefs}")


if __name__ == "__main__":
    np.random.seed(0)
    main()
