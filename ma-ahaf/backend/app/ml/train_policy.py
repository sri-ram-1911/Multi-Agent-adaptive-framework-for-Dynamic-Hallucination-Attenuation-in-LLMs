"""Learned ARCOP policy (proposal §8, §20 'learning-to-route controller').

Multi-output GradientBoosting mapping request signals -> 6 policy parameters.
Ships trained on synthetic rule-shaped data; retrain on production eval logs to
get a genuine learned router. The interpretable rule engine in
`app/controller/arcop.py` remains the default and the safety fallback.

    python -m app.ml.train_policy
"""

from __future__ import annotations

import os

import joblib
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split
from sklearn.multioutput import MultiOutputRegressor

from app.config import settings
from app.ml.features import POLICY_INPUTS, POLICY_OUTPUTS
from app.ml.synth_data import policy_dataset


def main() -> None:
    X, Y = policy_dataset()
    Xtr, Xte, Ytr, Yte = train_test_split(X, Y, test_size=0.2, random_state=0)
    model = MultiOutputRegressor(
        GradientBoostingRegressor(n_estimators=150, max_depth=3, learning_rate=0.06)
    )
    model.fit(Xtr, Ytr)
    mae = mean_absolute_error(Yte, model.predict(Xte))

    os.makedirs(settings.artifacts_dir, exist_ok=True)
    out = os.path.join(settings.artifacts_dir, "policy.joblib")
    joblib.dump(
        {"model": model, "inputs": POLICY_INPUTS, "outputs": POLICY_OUTPUTS,
         "mae": round(float(mae), 4)},
        out,
    )
    print(f"policy -> {out}  MAE={mae:.3f}")


if __name__ == "__main__":
    main()
