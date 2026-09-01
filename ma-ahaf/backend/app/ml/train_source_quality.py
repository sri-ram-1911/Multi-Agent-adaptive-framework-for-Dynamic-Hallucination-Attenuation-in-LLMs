"""Source-quality scorer (proposal §7 agent 7): GradientBoosting regressor over
[authority, freshness, relevance, consistency, corroboration] -> quality in [0,1].

    python -m app.ml.train_source_quality
"""

from __future__ import annotations

import os

import joblib
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split

from app.config import settings
from app.ml.features import SOURCE_FEATURES
from app.ml.synth_data import source_quality_dataset


def main() -> None:
    X, y = source_quality_dataset()
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=0)
    model = GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05)
    model.fit(Xtr, ytr)
    mae = mean_absolute_error(yte, model.predict(Xte))

    os.makedirs(settings.artifacts_dir, exist_ok=True)
    out = os.path.join(settings.artifacts_dir, "source_quality.joblib")
    joblib.dump({"model": model, "features": SOURCE_FEATURES, "mae": round(float(mae), 4)}, out)
    print(f"source_quality -> {out}  MAE={mae:.3f}")


if __name__ == "__main__":
    main()
