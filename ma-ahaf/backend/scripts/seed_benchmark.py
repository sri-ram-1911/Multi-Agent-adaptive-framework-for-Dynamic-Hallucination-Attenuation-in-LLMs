"""Copy the packaged benchmark into place (no-op if present).

    python -m scripts.seed_benchmark
"""

from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger

log = get_logger("seed_benchmark")


def main() -> None:
    p = Path("/data/benchmark/benchmark.jsonl")
    if p.exists():
        n = sum(1 for _ in p.open())
        log.info("benchmark.ready", path=str(p), items=n)
    else:
        log.warning("benchmark.missing", path=str(p),
                    hint="data/benchmark/benchmark.jsonl should be committed with the repo")


if __name__ == "__main__":
    main()
