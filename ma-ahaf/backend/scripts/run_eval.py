"""Run the evaluation harness from the CLI and write a JSON + CSV report.

    python -m scripts.run_eval --dataset data/benchmark/benchmark.jsonl --limit 40
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from app.core.logging import get_logger
from app.db.models import Tenant
from app.db.session import session_scope
from app.eval.harness import run_evaluation

log = get_logger("run_eval")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="data/benchmark/benchmark.jsonl")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--tenant", default="default")
    args = ap.parse_args()

    with session_scope() as db:
        tenant = db.query(Tenant).filter_by(name=args.tenant).one()
        summary, pareto = run_evaluation(db, tenant.id, args.dataset, limit=args.limit)

    run_dir = Path("artifacts/eval") / datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (run_dir / "pareto.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["system", "id", "type", "creativity", "reliability"])
        w.writeheader()
        w.writerows(pareto)

    print(json.dumps(summary.get("deltas", {}), indent=2))
    print(f"\nreport  -> {run_dir/'report.json'}")
    print(f"pareto  -> {run_dir/'pareto.csv'}")
    print(f"pareto frontier gain (MA-AHAF dominates baseline): "
          f"{summary.get('pareto_frontier_gain')}")


if __name__ == "__main__":
    main()
