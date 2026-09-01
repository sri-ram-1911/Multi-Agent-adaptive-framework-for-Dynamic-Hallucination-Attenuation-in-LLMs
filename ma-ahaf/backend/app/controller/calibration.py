"""Confidence calibration + confidence-evidence consistency check (proposal §5).

- `calibrate()` maps a raw confidence to an empirically calibrated probability
  (isotonic model trained by `bootstrap_models`, else a fixed power-law shrink).
- `consistency_gap()` flags responses whose stated confidence is disproportionate
  to evidence strength ("Confidence-Evidence Consistency Check").
- `ece()` is reported by the eval harness.
"""

from __future__ import annotations

import numpy as np

from app.ml import registry


def calibrate(raw_confidence: float) -> float:
    art = registry.load("calibrator.joblib")
    if art is not None:
        try:
            return float(np.clip(art.predict([raw_confidence])[0], 0.0, 1.0))
        except Exception:  # pragma: no cover
            pass
    return float(np.clip(raw_confidence**1.8 - 0.03, 0.0, 1.0))


def consistency_gap(stated_confidence: float, evidence_strength: float) -> float:
    """>0 means overconfident relative to evidence."""
    return float(stated_confidence - evidence_strength)


def ece(confidences: list[float], correct: list[int], *, bins: int = 10) -> float:
    if not confidences:
        return 0.0
    c = np.asarray(confidences)
    y = np.asarray(correct)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for i in range(bins):
        m = (c > edges[i]) & (c <= edges[i + 1])
        if m.any():
            total += m.mean() * abs(y[m].mean() - c[m].mean())
    return float(total)
