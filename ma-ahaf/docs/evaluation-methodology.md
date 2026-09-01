# Evaluation Methodology

Implements proposal §4 (evaluation framework) and §15 (success criteria).

## 1. Benchmark

`data/benchmark/benchmark.jsonl` — one JSON object per line:

```json
{"id": "h01", "type": "high_stakes",
 "prompt": "...", "reference": "gold answer",
 "gold_evidence": ["supporting passage text ..."],
 "labels": {"answerable": true, "expect_abstain_or_qualify": true}}
```

`type ∈ {factual, analytical, creative, mixed, high_stakes}`. The packaged set
has ~35 items across all five types, grounded in `data/corpus/`. Replace with a
client corpus + labelled prompts for a real engagement; splits are fixed for
reproducibility (NFR-11).

## 2. Systems compared

| System | Description |
|--------|-------------|
| `ma-ahaf` | Full pipeline via `run_pipeline` |
| `static-rag` | Same LLM + hybrid retriever, no adaptive control / verification / revision / abstention (`app/eval/baseline.py`) |

Ablations (extend `harness.py`): verification-depth sweep, revision loop on/off,
learned-vs-rule ARCOP, reranker on/off.

## 3. Metrics (`app/eval/metrics.py`)

**Reliability**
- `unsupported_claim_rate` — fraction of checkable claims with verdict ≠ supported
- `citation_precision` / `citation_recall` — supported ∧ overlaps a gold passage
- `entailment` — NLI entailment of the answer by the reference
- `ece` / `brier` — calibration of the (calibrated) confidence vs correctness

**Creativity**
- `distinct_2` — distinct bigram ratio
- `self_bleu` → `diversity = 1 − self_bleu` across candidates
- novelty vs the KB-evidence centroid (embedding distance)

**Cost**
- latency p50/p95, tokens, USD (from the gateway `UsageMeter` + `price_table`)

**Aggregate**
- `reliability_index ∈ [0,1]` = 0.45·(1−unsupported) + 0.25·citation_precision +
  0.20·entailment + 0.10·(1−ece)

## 4. Reliability–Creativity Pareto frontier (`app/eval/pareto.py`)

Each benchmark item becomes a point `(creativity, reliability)` per system.
`pareto_front` returns non-dominated points; `frontier_gain` = fraction of
baseline points that some MA-AHAF point Pareto-dominates. Target: `> 0` with no
collapse of creativity on the creative split.

## 5. Running

```bash
make eval                          # or:
docker compose exec api python -m scripts.run_eval --dataset data/benchmark/benchmark.jsonl --limit 40
```

Outputs `artifacts/eval/<timestamp>/report.json` + `pareto.csv`. The dashboard
**Evaluation** page triggers a run (`POST /v1/eval/run`) and renders the deltas,
Pareto scatter and full report.

## 6. Interpreting results

- `deltas.unsupported_rate` should be **negative** (MA-AHAF lower).
- `deltas.citation_precision`, `deltas.reliability`, `deltas.creativity` on the
  creative split should be **≥ 0**.
- On items with `labels.answerable == false`, MA-AHAF should mostly `abstain` or
  `qualify` (check `by_action` and per-item actions in the trace list).
- Latency/cost will be **higher** for MA-AHAF — that is the reliability/creativity
  trade the framework makes visible and controllable, not free.
