"""Synthetic labelled data generators.

Real client eval logs are the intended training source. Until those exist these
generators let ``make train-models`` produce sensible artifacts so the system is
runnable out of the box. Each generative process encodes the domain priors from
the proposal (§9 risk model, §8 controller, §7 source quality).
"""

from __future__ import annotations

import numpy as np

from app.ml.features import CLAIM_TYPES

rng = np.random.default_rng(42)


def risk_dataset(n: int = 4000) -> tuple[np.ndarray, np.ndarray]:
    """Features -> P(claim unsupported). Weights mirror proposal §9 intent."""
    X = rng.random((n, 7))
    # emphasise evidence + contradiction + criticality
    w = np.array([1.6, 1.9, 1.1, 0.9, 1.3, 0.7, 1.4])
    logits = X @ w - 3.1 + rng.normal(0, 0.35, n)
    p = 1 / (1 + np.exp(-logits))
    y = (rng.random(n) < p).astype(int)
    return X, y


def claim_type_dataset(n: int = 1800) -> tuple[list[str], list[str]]:
    templates = {
        "factual": ["The capital of {x} is {y}.", "{x} was founded in {y}.", "{x} is located in {y}."],
        "numeric": ["{x} costs {y} dollars.", "The dose of {x} is {y} mg.", "{x} grew by {y} percent."],
        "causal": ["{x} causes {y}.", "Because of {x}, {y} happened.", "{x} leads to {y}."],
        "temporal": ["As of {y}, {x} is the latest version.", "{x} will be released in {y}.",
                     "Since {y}, {x} has changed."],
        "opinion": ["{x} is the best option for {y}.", "I think {x} is better than {y}.",
                    "{x} seems overrated compared to {y}."],
        "creative": ["Imagine {x} dancing with {y} under a violet sky.",
                     "A story where {x} befriends {y}.", "Picture {x} as a metaphor for {y}."],
    }
    xs = ["the system", "the drug", "the company", "the model", "the city", "the policy"]
    ys = ["2024", "Paris", "42", "growth", "the market", "the user"]
    texts, labels = [], []
    for _ in range(n):
        t = CLAIM_TYPES[rng.integers(len(CLAIM_TYPES))]
        tmpl = templates[t][rng.integers(len(templates[t]))]
        texts.append(tmpl.format(x=xs[rng.integers(len(xs))], y=ys[rng.integers(len(ys))]))
        labels.append(t)
    return texts, labels


def source_quality_dataset(n: int = 3000) -> tuple[np.ndarray, np.ndarray]:
    """[authority, freshness, relevance, consistency, corroboration] -> quality in [0,1]."""
    X = rng.random((n, 5))
    w = np.array([0.30, 0.15, 0.25, 0.15, 0.15])
    y = np.clip(X @ w + rng.normal(0, 0.06, n), 0, 1)
    return X, y


def policy_dataset(n: int = 5000) -> tuple[np.ndarray, np.ndarray]:
    """Inputs (proposal §8) -> 6 policy parameters. Rule-shaped targets + noise so a
    regressor can learn a smooth 'learning-to-route' surface."""
    risk, amb, crit, creativ, cov, agree, conf = (rng.random(n) for _ in range(7))
    X = np.stack([risk, amb, crit, creativ, cov, agree, conf], axis=1)

    grounding = np.clip(0.35 + 0.5 * risk + 0.3 * crit - 0.25 * creativ, 0, 1)
    verify = np.clip(0.2 + 0.6 * risk + 0.4 * crit + 0.3 * (1 - agree) - 0.3 * creativ, 0, 1)
    creativity_allow = np.clip(0.15 + 0.8 * creativ - 0.4 * risk - 0.3 * crit, 0, 1)
    citation = np.clip(0.2 + 0.7 * crit + 0.4 * risk - 0.3 * creativ, 0, 1)
    abstain = np.clip(0.2 + 0.45 * crit + 0.35 * risk - 0.3 * cov, 0.05, 0.9)
    escalate = np.clip(0.3 + 0.4 * risk + 0.3 * crit + 0.2 * (1 - agree), 0.1, 0.95)
    Y = np.stack([grounding, verify, creativity_allow, citation, abstain, escalate], axis=1)
    Y += rng.normal(0, 0.03, Y.shape)
    return X, np.clip(Y, 0, 1)


def calibration_dataset(n: int = 2000) -> tuple[np.ndarray, np.ndarray]:
    """Raw confidence (overconfident) -> correctness label, for Platt/isotonic."""
    raw = np.clip(rng.beta(5, 2, n), 0, 1)          # model tends high
    true_p = np.clip(raw**1.8 - 0.05, 0, 1)          # actually lower
    y = (rng.random(n) < true_p).astype(int)
    return raw, y
