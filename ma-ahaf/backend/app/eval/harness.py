"""Evaluation harness — run MA-AHAF vs the static-RAG baseline over a benchmark
and compute the reliability / creativity / cost metrics + Pareto frontier.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.eval import metrics as M
from app.eval.baseline import static_rag
from app.eval.datasets import load_jsonl, split_by_type
from app.eval.pareto import frontier_gain, pareto_front
from app.orchestration.pipeline import run_pipeline

log = get_logger("eval")


def _row_metrics_maahaf(state, row: dict) -> dict:
    claims = [c.model_dump() for c in state.claim_graph.claims]
    prec, rec = M.citation_pr(claims, row.get("gold_evidence", []))
    ent = M.entailment_accuracy(state.final_response, row.get("reference", ""))
    creativ = M.creativity_scores(state.final_response, state.candidates)
    m = {
        "unsupported_rate": round(M.unsupported_claim_rate(claims), 3),
        "citation_precision": round(prec, 3),
        "citation_recall": round(rec, 3),
        "entailment": round(0.0 if ent != ent else ent, 3),
        "abstained": state.action in ("abstain", "escalate"),
        "calibrated_confidence": state.calibrated_confidence,
        "creativity": creativ["distinct_2"] * 0.5 + creativ["diversity"] * 0.5,
        "latency_ms": state.__dict__.get("_latency_ms", 0),
        "tokens": getattr(state.__dict__.get("_usage"), "total_tokens", 0),
        "cost_usd": round(getattr(state.__dict__.get("_usage"), "cost_usd", 0.0), 5),
    }
    m["ece"] = 0.0
    m["reliability"] = round(M.reliability_index(m), 3)
    return m


def _row_metrics_baseline(out: dict, row: dict) -> dict:
    # baseline has no claim graph; approximate unsupported rate via entailment of
    # the answer against its own retrieved evidence
    ent_ref = M.entailment_accuracy(out["response"], row.get("reference", ""))
    supported = M.entailment_accuracy(
        out["response"], " ".join(e.text for e in out["evidence"][:3])
    )
    creativ = M.creativity_scores(out["response"])
    m = {
        "unsupported_rate": round(1 - supported, 3),
        "citation_precision": round(supported, 3),
        "citation_recall": round(supported, 3),
        "entailment": round(0.0 if ent_ref != ent_ref else ent_ref, 3),
        "abstained": False,
        "calibrated_confidence": out["confidence"],
        "creativity": creativ["distinct_2"] * 0.5 + creativ["diversity"] * 0.5,
        "latency_ms": out["latency_ms"],
        "tokens": out["usage"].total_tokens,
        "cost_usd": round(out["usage"].cost_usd, 5),
        "ece": 0.0,
    }
    m["reliability"] = round(M.reliability_index(m), 3)
    return m


def _aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {}
    keys = ["unsupported_rate", "citation_precision", "citation_recall", "entailment",
            "reliability", "creativity", "calibrated_confidence", "latency_ms",
            "tokens", "cost_usd"]
    agg = {k: round(sum(r[k] for r in rows) / len(rows), 4) for k in keys}
    agg["abstention_rate"] = round(sum(r["abstained"] for r in rows) / len(rows), 3)
    conf = [r["calibrated_confidence"] for r in rows]
    correct = [1 - int(r["unsupported_rate"] > 0.5) for r in rows]
    agg.update(M.calibration_metrics(conf, correct))
    return agg


def run_evaluation(
    db: Session, tenant_id: str, dataset: str, *, limit: int = 40
) -> tuple[dict, list[dict]]:
    rows = load_jsonl(dataset)[:limit]
    maahaf_rows: list[dict] = []
    baseline_rows: list[dict] = []
    pareto_points: list[dict] = []

    for i, row in enumerate(rows):
        log.info("eval.item", i=i, total=len(rows), type=row.get("type"))
        try:
            state = run_pipeline(db, tenant_id=tenant_id, prompt=row["prompt"], persist=False)
            m = _row_metrics_maahaf(state, row)
            maahaf_rows.append(m)
            pareto_points.append({"system": "ma-ahaf", "id": row.get("id", i),
                                  "creativity": round(m["creativity"], 3),
                                  "reliability": m["reliability"], "type": row.get("type")})
        except Exception as exc:  # pragma: no cover
            log.warning("eval.maahaf_failed", i=i, error=str(exc))

        try:
            out = static_rag(db, tenant_id, row["prompt"])
            b = _row_metrics_baseline(out, row)
            baseline_rows.append(b)
            pareto_points.append({"system": "static-rag", "id": row.get("id", i),
                                  "creativity": round(b["creativity"], 3),
                                  "reliability": b["reliability"], "type": row.get("type")})
        except Exception as exc:  # pragma: no cover
            log.warning("eval.baseline_failed", i=i, error=str(exc))

    by_type = split_by_type(rows)
    summary = {
        "n": len(rows),
        "by_type_counts": {k: len(v) for k, v in by_type.items()},
        "ma_ahaf": _aggregate(maahaf_rows),
        "static_rag": _aggregate(baseline_rows),
        "deltas": {},
        "pareto_frontier_gain": frontier_gain(
            [p for p in pareto_points if p["system"] == "ma-ahaf"],
            [p for p in pareto_points if p["system"] == "static-rag"],
        ),
    }
    if summary["ma_ahaf"] and summary["static_rag"]:
        summary["deltas"] = {
            "unsupported_rate": round(
                summary["ma_ahaf"]["unsupported_rate"] - summary["static_rag"]["unsupported_rate"], 4
            ),
            "citation_precision": round(
                summary["ma_ahaf"]["citation_precision"] - summary["static_rag"]["citation_precision"], 4
            ),
            "ece": round(summary["ma_ahaf"]["ece"] - summary["static_rag"]["ece"], 4),
            "creativity": round(
                summary["ma_ahaf"]["creativity"] - summary["static_rag"]["creativity"], 4
            ),
            "reliability": round(
                summary["ma_ahaf"]["reliability"] - summary["static_rag"]["reliability"], 4
            ),
        }
    summary["pareto_front"] = pareto_front(pareto_points)
    return summary, pareto_points
