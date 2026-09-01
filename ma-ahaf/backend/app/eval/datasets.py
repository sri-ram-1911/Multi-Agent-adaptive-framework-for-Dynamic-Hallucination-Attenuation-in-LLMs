"""Benchmark loading. Format: JSONL with one object per line:

    {"id", "prompt", "type", "reference", "gold_evidence": [str], "labels": {...}}

`type` is one of factual|analytical|creative|mixed|high_stakes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_jsonl(path: str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"benchmark not found: {path} (run `make seed`)")
    with p.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def split_by_type(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r.get("type", "factual"), []).append(r)
    return out
