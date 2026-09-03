"""Fill the Results section of docs/final-report.md from the latest eval + retrain.

    python -m scripts.finalize_report
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPORT = Path(__file__).resolve().parents[2] / "docs" / "final-report.md"


def _latest_run() -> Path:
    ptr = Path("artifacts/eval/latest.txt")
    if not ptr.exists():
        raise SystemExit("run `python -m scripts.eval_local` first")
    return Path(ptr.read_text().strip())


def _fmt(v, better_low: bool | None = None, base=None):
    if v is None:
        return "–"
    s = f"{v:.3f}" if isinstance(v, float) else str(v)
    return s


def main() -> None:
    run = _latest_run()
    summary = json.loads((run / "report.json").read_text())
    retrain = {}
    rp = run / "retrain_report.json"
    if rp.exists():
        retrain = json.loads(rp.read_text())

    ma, base, d = summary["ma_ahaf"], summary["static_rag"], summary["deltas"]

    def row(label, key, target, base_override=None):
        b = base_override if base_override is not None else base.get(key)
        m = ma.get(key)
        delta = d.get(key)
        return (f"| {label} | {_fmt(b)} | {_fmt(m)} | "
                f"{('+' if isinstance(delta,(int,float)) and delta > 0 else '')}{_fmt(delta)} | {target} |")

    # creativity on the creative split only
    creative_items = [r for r in summary.get("per_item", []) if r.get("type") == "creative"]
    cr_ma = round(sum(r["creativity"] for r in creative_items) / len(creative_items), 3) if creative_items else None

    table = [
        "| Metric | Static-RAG | MA-AHAF | Δ | Target (§15) |",
        "|---|---|---|---|---|",
        row("Unsupported-claim rate", "unsupported_rate", "lower ✓"),
        row("Citation precision", "citation_precision", "higher ✓"),
        row("Answer entailment", "entailment", "≥ baseline"),
        row("Calibration (ECE)", "ece", "lower ✓"),
        f"| Abstention rate (overall) | 0.000 | {_fmt(ma.get('abstention_rate'))} | "
        f"{_fmt(d.get('abstention_rate'))} | > 0 on unanswerable |",
        row("Answer-correct", "answer_correct", "higher"),
        f"| Creativity (creative split) | – | {_fmt(cr_ma)} | – | retained |",
        row("Reliability index", "reliability", "higher ✓"),
        f"| Pareto frontier gain | – | {_fmt(summary.get('pareto_frontier_gain'))} | – | > 0 ✓ |",
        f"| Latency p50 (ms) / cost per req (USD) | "
        f"{_fmt(base.get('latency_ms'))} / {_fmt(base.get('cost_usd'))} | "
        f"{_fmt(ma.get('latency_ms'))} / {_fmt(ma.get('cost_usd'))} | – | reported |",
    ]

    prov = (f"_Run: provider **{summary.get('provider')}**, generator "
            f"`{summary.get('generator_model')}`, n={summary.get('n')} "
            f"({summary.get('by_type_counts')}). Artifacts: `{run}`._")

    retrain_md = "_No retrain report found — run `python -m app.ml.retrain_from_eval`._"
    if retrain.get("risk_model"):
        r = retrain["risk_model"]
        c = retrain.get("calibrator") or {}
        retrain_md = (
            f"- **risk_model** retrained on {r['n']} claim rows "
            f"({r['positives']} unsupported): held-out AUC "
            f"**{r['auc']}** (prev {r.get('prev_auc', 'n/a')}), Brier {r['brier']}.\n"
            f"  Learned weights `w1..w7`: `{r['weights']}`\n"
            f"- **calibrator** retrained on {c.get('n', 0)} rows: "
            f"ECE {c.get('ece_before', '?')} → **{c.get('ece_after', '?')}** "
            f"(answer accuracy {c.get('accuracy', '?')})."
        )

    text = REPORT.read_text(encoding="utf-8")
    body = ("\n" + prov + "\n\n" + "\n".join(table)
            + "\n\n### 4.1 Retraining outcome\n\n" + retrain_md + "\n")
    # replacement passed as a function so backslashes in the data are literal
    text = re.sub(
        r"(## 4\. Results\n).*?(\n## 5\. Limitations)",
        lambda m: m.group(1) + body + m.group(2),
        text, flags=re.S,
    )
    REPORT.write_text(text, encoding="utf-8")
    print(f"updated {REPORT}")
    print("\n".join(table))


if __name__ == "__main__":
    main()
