"""Benchmark loading. Format: JSONL with one object per line:

    {"id", "prompt", "type", "reference", "gold_evidence": [str], "labels": {...}}

`type` is one of factual|analytical|creative|mixed|high_stakes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_jsonl(path: str) -> list[dict[str, Any]]:
    """Load a JSONL benchmark file, or every ``*.jsonl`` in a directory.

    When ``path`` names a file inside a directory that also holds sibling
    ``benchmark_*.jsonl`` files, those are merged in too (de-duped by ``id``).
    """
    p = Path(path)
    files: list[Path]
    if p.is_dir():
        files = sorted(p.glob("*.jsonl"))
    elif p.exists():
        files = [p, *sorted(f for f in p.parent.glob("benchmark_*.jsonl") if f != p)]
    else:
        raise FileNotFoundError(f"benchmark not found: {path} (run `make seed`)")

    rows: dict[str, dict[str, Any]] = {}
    for f in files:
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    obj = json.loads(line)
                    rows[str(obj.get("id", f"{f.name}:{len(rows)}"))] = obj
    return list(rows.values())


def split_by_type(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r.get("type", "factual"), []).append(r)
    return out
