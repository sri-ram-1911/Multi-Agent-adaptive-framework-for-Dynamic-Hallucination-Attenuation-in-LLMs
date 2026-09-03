"""Evaluation harness that runs WITHOUT Postgres — MA-AHAF vs static-RAG over the
benchmark, using the in-memory corpus and whatever LLM provider is configured
(local flan-t5 by default; set MAAHAF_LLM__PROVIDER=openai for the GPT-4o run).

Emits, under artifacts/eval/<ts>/:
  report.json         aggregate metrics + deltas + Pareto frontier gain
  pareto.csv          (system, id, type, creativity, reliability) per item
  training_rows.jsonl claim-level (risk features -> unsupported label) for retraining
  calibration_rows.jsonl (raw confidence -> correct) for the calibrator

    python -m scripts.eval_local --limit 30 --model google/flan-t5-base
    MAAHAF_LLM__PROVIDER=openai python -m scripts.eval_local --limit 77
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_argv = sys.argv[1:]
if "--model" in _argv:
    os.environ["MAAHAF_LLM__HF_MODEL"] = _argv[_argv.index("--model") + 1]
os.environ.setdefault("MAAHAF_LLM__PROVIDER", "hf")
os.environ.setdefault("MAAHAF_OTEL_ENABLED", "false")
os.environ.setdefault("MAAHAF_LOG_LEVEL", "WARNING")
# local ML models (embeddings, rerank, zero-shot intent) run on CPU regardless of
# the LLM provider — keep them cached/offline and use the small zero-shot head so
# the harness is not bottlenecked by a 1.6 GB bart-large download + slow inference.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("MAAHAF_ZEROSHOT_MODEL",
                      "MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33")
os.environ.setdefault("MAAHAF_MAX_REVISION_LOOPS", "1")

import numpy as np  # noqa: E402

from app.config import settings  # noqa: E402
from app.core.logging import get_logger  # noqa: E402
from app.eval import metrics as M  # noqa: E402
from app.eval.baseline import static_rag  # noqa: E402
from app.eval.datasets import load_jsonl, split_by_type  # noqa: E402
from app.eval.pareto import frontier_gain, pareto_front  # noqa: E402
from app.ml.features import RISK_FEATURES, risk_vector  # noqa: E402
from app.nlp.nli import entail  # noqa: E402
from app.orchestration import nodes as N  # noqa: E402
from app.orchestration.pipeline import run_pipeline  # noqa: E402

log = get_logger("eval_local")

CORPUS_DIR = os.environ.get("MAAHAF_CORPUS_DIR", "/data/corpus")
if not os.path.isdir(CORPUS_DIR):
    CORPUS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "corpus")
BENCH = os.path.join(os.path.dirname(CORPUS_DIR), "benchmark", "benchmark.jsonl")


def _wire_local_corpus():
    from app.retrieval.local_store import LocalCorpus

    corpus = LocalCorpus.from_dir(CORPUS_DIR)

    def pre_retrieve(s):
        if s.policy and s.policy.grounding_intensity >= 0.45:
            s.evidence = corpus.retrieve(s.prompt, k=8, rerank_k=5)
        return s

    def retrieve(s):
        pool = corpus.retrieve_multi([s.prompt], k=10, rerank_k=6)
        s.evidence = pool
        for c in s.claim_graph.claims:
            if c.claim_type not in ("creative", "opinion"):
                c.evidence_ids = [e.chunk_id for e in pool[:5]]
        s.signals.evidence_coverage = 1.0 if pool else 0.0
        sc = [e.source_score for e in pool] or [0.5]
        s.signals.source_agreement = round(1 - (max(sc) - min(sc)), 3)
        return s

    N.n_pre_retrieve = pre_retrieve
    N.n_retrieve = retrieve
    from app.eval.baseline import set_local_corpus

    set_local_corpus(corpus)
    return corpus


def _claim_unsupported(claim_text: str, row: dict) -> int:
    """Ground-truth label: is this claim NOT supported by the gold evidence / reference?"""
    gold = " ".join(row.get("gold_evidence", []) or []) or row.get("reference", "")
    if not gold:
        return 1  # unanswerable item -> any concrete factual claim is unsupported
    return int(entail(gold, claim_text)["entailment"] < 0.5)


def _maahaf_row(state, row: dict, train_sink: list, calib_sink: list) -> dict:
    claims = state.claim_graph.claims
    checkable = [c for c in claims if c.claim_type not in ("creative", "opinion")]

    # collect retraining data (real features -> real label)
    unsupported_flags = []
    for c in checkable:
        label = _claim_unsupported(c.text, row)
        unsupported_flags.append(label)
        signals = {
            "evidence_coverage": c.evidence_coverage,
            "contradiction_score": c.contradiction_score,
            "source_agreement": c.source_agreement,
            "model_uncertainty": c.model_uncertainty,
            "criticality": c.criticality,
            "temporal_sensitivity": c.temporal_sensitivity,
            "agent_disagreement": c.agent_disagreement,
        }
        train_sink.append({
            "features": dict(zip(RISK_FEATURES, risk_vector(signals).tolist(), strict=True)),
            "unsupported": label,
            "predicted_risk": c.risk_score,
        })

    unsupported_rate = float(np.mean(unsupported_flags)) if unsupported_flags else 0.0
    prec, rec = M.citation_pr([c.model_dump() for c in claims], row.get("gold_evidence", []))
    ent = (
        M.entailment_accuracy(state.final_response, row["reference"])
        if row.get("reference") else float("nan")
    )
    creativ = M.creativity_scores(state.final_response, state.candidates)

    # the item is "correct" if the model answered and didn't leave unsupported critical claims
    answerable = row.get("labels", {}).get("answerable", True)
    correct = int(
        (state.action in ("answer", "qualify") and unsupported_rate < 0.5) if answerable
        else state.action in ("abstain", "escalate")
    )
    calib_sink.append({"raw_confidence": state.confidence, "correct": correct})

    m = {
        "id": row.get("id"), "type": row.get("type"),
        "unsupported_rate": round(unsupported_rate, 3),
        "citation_precision": round(prec, 3), "citation_recall": round(rec, 3),
        "entailment": round(0.0 if ent != ent else ent, 3),
        "abstained": state.action in ("abstain", "escalate"),
        "answer_correct": correct,
        "calibrated_confidence": state.calibrated_confidence,
        "creativity": round(creativ["distinct_2"] * 0.5 + creativ["diversity"] * 0.5, 3),
        "latency_ms": state.__dict__.get("_latency_ms", 0),
        "tokens": getattr(state.__dict__.get("_usage"), "total_tokens", 0),
        "cost_usd": round(getattr(state.__dict__.get("_usage"), "cost_usd", 0.0), 5),
        "ece": 0.0,
    }
    m["reliability"] = round(M.reliability_index(m), 3)
    return m


def _baseline_row(out: dict, row: dict) -> dict:
    ent_ref = M.entailment_accuracy(out["response"], row.get("reference", "")) if row.get("reference") else float("nan")
    supported = M.entailment_accuracy(out["response"], " ".join(e.text for e in out["evidence"][:3])) \
        if out["evidence"] else 0.0
    creativ = M.creativity_scores(out["response"])
    answerable = row.get("labels", {}).get("answerable", True)
    correct = int(supported >= 0.5) if answerable else 0  # baseline never abstains
    m = {
        "id": row.get("id"), "type": row.get("type"),
        "unsupported_rate": round(1 - supported, 3),
        "citation_precision": round(supported, 3), "citation_recall": round(supported, 3),
        "entailment": round(0.0 if ent_ref != ent_ref else ent_ref, 3),
        "abstained": False, "answer_correct": correct,
        "calibrated_confidence": out["confidence"],
        "creativity": round(creativ["distinct_2"] * 0.5 + creativ["diversity"] * 0.5, 3),
        "latency_ms": out["latency_ms"], "tokens": out["usage"].total_tokens,
        "cost_usd": round(out["usage"].cost_usd, 5), "ece": 0.0,
    }
    m["reliability"] = round(M.reliability_index(m), 3)
    return m


def _aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {}
    keys = ["unsupported_rate", "citation_precision", "citation_recall", "entailment",
            "reliability", "creativity", "calibrated_confidence", "answer_correct",
            "latency_ms", "tokens", "cost_usd"]
    agg = {k: round(float(np.mean([r[k] for r in rows])), 4) for k in keys}
    agg["abstention_rate"] = round(float(np.mean([r["abstained"] for r in rows])), 3)
    conf = [r["calibrated_confidence"] for r in rows]
    corr = [r["answer_correct"] for r in rows]
    agg.update(M.calibration_metrics(conf, corr))
    agg["n"] = len(rows)
    return agg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--model", default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=90, help="per-item wall-clock cap (s)")
    args, _ = ap.parse_known_args()

    _wire_local_corpus()
    rows = load_jsonl(BENCH)
    rng = np.random.default_rng(args.seed)
    rng.shuffle(rows)
    rows = rows[: args.limit]

    from concurrent.futures import ThreadPoolExecutor

    def _guarded(fn):
        """Run fn() in a throwaway worker thread with a hard wall-clock cap so a
        stuck local-model call can't hang the whole evaluation. A timed-out
        thread is abandoned (daemon) — `os._exit` at the end skips the join."""
        ex = ThreadPoolExecutor(max_workers=1)
        try:
            return ex.submit(fn).result(timeout=args.timeout)
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

    m_rows, b_rows, pareto, train_sink, calib_sink = [], [], [], [], []
    timeouts = 0
    for i, row in enumerate(rows):
        log.warning("eval.item", i=i + 1, n=len(rows), id=row.get("id"), type=row.get("type"))
        st = None
        try:
            st = _guarded(lambda r=row: run_pipeline(None, tenant_id="eval", prompt=r["prompt"],
                                                     persist=False))
        except TimeoutError:
            timeouts += 1
            log.error("eval.maahaf_timeout", id=row.get("id"), seconds=args.timeout)
        except Exception as exc:  # pragma: no cover
            log.error("eval.maahaf_failed", id=row.get("id"), error=str(exc))
        if st is not None:
            try:
                mr = _maahaf_row(st, row, train_sink, calib_sink)
                m_rows.append(mr)
                pareto.append({"system": "ma-ahaf", "id": row.get("id"), "type": row.get("type"),
                               "creativity": mr["creativity"], "reliability": mr["reliability"]})
            except Exception as exc:  # pragma: no cover
                log.error("eval.maahaf_metrics_failed", id=row.get("id"), error=str(exc))
        try:
            out = _guarded(lambda r=row: static_rag(None, "eval", r["prompt"]))
            br = _baseline_row(out, row)
            b_rows.append(br)
            pareto.append({"system": "static-rag", "id": row.get("id"), "type": row.get("type"),
                           "creativity": br["creativity"], "reliability": br["reliability"]})
        except Exception as exc:  # pragma: no cover
            log.error("eval.baseline_failed", id=row.get("id"), error=str(exc))

    ma, base = _aggregate(m_rows), _aggregate(b_rows)
    generator = (settings.llm.hf_model if settings.llm.provider == "hf"
                 else settings.llm.generator_model)
    summary = {
        "provider": settings.llm.provider,
        "generator_model": generator,
        "n": len(rows),
        "completed": len(m_rows),
        "timeouts": timeouts,
        "config": {"revision_loops": settings.max_revision_loops,
                   "verifier_llm_enabled": settings.verifier_llm_enabled,
                   "per_item_timeout_s": args.timeout},
        "by_type_counts": {k: len(v) for k, v in split_by_type(rows).items()},
        "ma_ahaf": ma, "static_rag": base,
        "deltas": {
            k: round(ma.get(k, 0) - base.get(k, 0), 4)
            for k in ("unsupported_rate", "citation_precision", "entailment", "ece",
                      "creativity", "reliability", "answer_correct", "abstention_rate")
        } if ma and base else {},
        "pareto_frontier_gain": frontier_gain(
            [p for p in pareto if p["system"] == "ma-ahaf"],
            [p for p in pareto if p["system"] == "static-rag"],
        ),
        "pareto_front": pareto_front(pareto),
        "per_item": m_rows,
    }

    run_dir = Path("artifacts/eval") / datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (run_dir / "pareto.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["system", "id", "type", "creativity", "reliability"])
        w.writeheader()
        w.writerows(pareto)
    (run_dir / "training_rows.jsonl").write_text(
        "\n".join(json.dumps(r) for r in train_sink), encoding="utf-8")
    (run_dir / "calibration_rows.jsonl").write_text(
        "\n".join(json.dumps(r) for r in calib_sink), encoding="utf-8")
    # stable "latest" pointer
    (Path("artifacts/eval") / "latest.txt").write_text(str(run_dir), encoding="utf-8")

    print(json.dumps({"completed": len(m_rows), "timeouts": timeouts,
                      "deltas": summary["deltas"],
                      "pareto_frontier_gain": summary["pareto_frontier_gain"],
                      "ma_ahaf": ma, "static_rag": base}, indent=2))
    print(f"\nwrote {run_dir}")


if __name__ == "__main__":
    try:
        main()
    finally:
        # abandon any timed-out worker threads instead of blocking on join at exit
        os._exit(0)
