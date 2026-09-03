"""Retrain the hallucination risk model + confidence calibrator on data produced
by a real evaluation run (proposal §8/§9: "upgraded to a learned policy using
historical evaluation data", weights "calibrated using a held-out evaluation set").

    python -m app.ml.retrain_from_eval                     # uses artifacts/eval/latest.txt
    python -m app.ml.retrain_from_eval artifacts/eval/20260901T120000
"""

from __future__ import annotations

import contextlib
import json
import os
import sys

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split

from app.config import settings
from app.core.logging import get_logger
from app.ml import registry
from app.ml.features import RISK_FEATURES

log = get_logger("ml.retrain")


def _run_dir() -> str:
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        return sys.argv[1]
    ptr = os.path.join("artifacts", "eval", "latest.txt")
    if not os.path.exists(ptr):
        raise SystemExit("no artifacts/eval/latest.txt — run `python -m scripts.eval_local` first")
    return open(ptr).read().strip()


def _load_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    return [json.loads(x) for x in open(path, encoding="utf-8") if x.strip()]


def retrain_risk_model(run_dir: str) -> dict | None:
    rows = _load_jsonl(os.path.join(run_dir, "training_rows.jsonl"))
    if len(rows) < 40:
        log.warning("retrain.risk.too_few_rows", n=len(rows))
        return None
    X = np.array([[r["features"][f] for f in RISK_FEATURES] for r in rows], dtype=float)
    y = np.array([r["unsupported"] for r in rows], dtype=int)
    if len(set(y)) < 2:
        log.warning("retrain.risk.single_class", positives=int(y.sum()))
        return None

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=0, stratify=y)
    base = LogisticRegression(max_iter=1000, C=1.0, class_weight="balanced")
    base.fit(Xtr, ytr)
    clf = CalibratedClassifierCV(base, method="isotonic", cv=3)
    clf.fit(Xtr, ytr)
    proba = clf.predict_proba(Xte)[:, 1]

    # baseline (old model) numbers on the same test split, for the report
    old = registry.load("risk_model.joblib")
    old_auc = None
    if old is not None:
        with contextlib.suppress(Exception):  # pragma: no cover
            old_auc = round(float(roc_auc_score(yte, old["model"].predict_proba(Xte)[:, 1])), 4)

    coefs = dict(zip(RISK_FEATURES, base.coef_[0].round(3).tolist(), strict=True))
    # write next to the eval run, not over the shipped default: a small benchmark
    # fit is for inspection, not for production. Pass --promote to install it.
    fname = "risk_model.joblib" if "--promote" in sys.argv else "risk_model.retrained.joblib"
    dest_dir = settings.artifacts_dir if "--promote" in sys.argv else run_dir
    out = os.path.join(dest_dir, fname)
    joblib.dump({"model": clf, "linear": base, "features": RISK_FEATURES, "coef": coefs,
                 "intercept": float(base.intercept_[0]),
                 "metrics": {"auc": round(float(roc_auc_score(yte, proba)), 4),
                             "brier": round(float(brier_score_loss(yte, proba)), 4),
                             "n_train": len(ytr), "trained_on": "eval:" + os.path.basename(run_dir)}},
                out)
    return {"n": len(rows), "positives": int(y.sum()),
            "auc": round(float(roc_auc_score(yte, proba)), 4),
            "brier": round(float(brier_score_loss(yte, proba)), 4),
            "prev_auc": old_auc, "weights": coefs}


def retrain_calibrator(run_dir: str) -> dict | None:
    rows = _load_jsonl(os.path.join(run_dir, "calibration_rows.jsonl"))
    if len(rows) < 20:
        log.warning("retrain.calib.too_few_rows", n=len(rows))
        return None
    raw = np.array([r["raw_confidence"] for r in rows], dtype=float)
    y = np.array([r["correct"] for r in rows], dtype=int)
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(raw, y)
    cname = "calibrator.joblib" if "--promote" in sys.argv else "calibrator.retrained.joblib"
    cdir = settings.artifacts_dir if "--promote" in sys.argv else run_dir
    joblib.dump(iso, os.path.join(cdir, cname))

    def _ece(conf, corr, bins=10):
        conf, corr = np.asarray(conf), np.asarray(corr)
        edges = np.linspace(0, 1, bins + 1)
        tot = 0.0
        for i in range(bins):
            m = (conf > edges[i]) & (conf <= edges[i + 1])
            if m.any():
                tot += m.mean() * abs(corr[m].mean() - conf[m].mean())
        return round(float(tot), 4)

    return {"n": len(rows), "accuracy": round(float(y.mean()), 3),
            "ece_before": _ece(raw, y), "ece_after": _ece(iso.predict(raw), y)}


def main() -> None:
    run_dir = _run_dir()
    log.warning("retrain.start", run_dir=run_dir)
    risk = retrain_risk_model(run_dir)
    calib = retrain_calibrator(run_dir)
    registry.clear()
    report = {"run_dir": run_dir, "risk_model": risk, "calibrator": calib}
    with open(os.path.join(run_dir, "retrain_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
