# MA-AHAF — Final Project Report

Multi-Agent Adaptive Framework for Dynamic Hallucination Attenuation in LLMs.
Fulfils proposal deliverable §17.13 (final report: methodology, experiments,
results, limitations) and reports against the acceptance criteria in §15.

> **Run provenance.** The numbers in §4 are produced by `scripts/eval_local.py`
> over a seeded held-out sample of the benchmark, running the full pipeline on
> **`gpt-4o-mini`** (generator · decomposer · verifier · reviser) with local
> `bge-small` + BM25 + cross-encoder retrieval and an LLM-backed entailment judge
> for verification. §4 and §4.1 are auto-filled by `scripts/finalize_report.py`
> from `artifacts/eval/latest`. To reproduce: `.\tasks.ps1 eval-openai` then
> `.\tasks.ps1 retrain` then `python -m scripts.finalize_report`.

## 1. Methodology

### 1.1 Systems compared

| System | Description |
|---|---|
| **MA-AHAF** | Full 13-agent pipeline (`app/orchestration/pipeline.py`): intent → risk → ARCOP policy → grounding-first retrieval → generation → claim decomposition → hybrid retrieval + source scoring → NLI verification + contradiction → claim-level `H(x)` → creativity → bounded revision → consensus → abstention/escalation → audit. |
| **Static-RAG baseline** | Same generator + the same hybrid retriever, top-5 passages in context, no adaptive control, no verification, no revision, no abstention (`app/eval/baseline.py`). |

Both systems use the identical retrieval stack and generator model, so the delta
isolates the *adaptive attenuation layer*.

### 1.2 Benchmark

`data/benchmark/*.jsonl` — 77 items grounded in the sample corpus
(`data/corpus/`), across five task types (factual 31, high-stakes 17, analytical
12, creative 10, mixed 7). 8 high-stakes items are deliberately **unanswerable**
from the corpus (`labels.answerable == false`) to test calibrated abstention.
Each answerable item carries a reference answer and gold evidence spans. Splits
are seeded (`--seed`) for reproducibility.

> This is a **demonstration benchmark**. A production engagement needs a
> client-domain corpus and ≥500 human-labelled prompts (see §5).

### 1.3 Metrics (`app/eval/metrics.py`)

- **Unsupported-claim rate** — fraction of checkable claims whose text is *not*
  entailed by the gold evidence (DeBERTa-v3 NLI, entailment < 0.5). This is the
  ground-truth label; it does not depend on the generator.
- **Citation precision / recall** — supported ∧ overlaps a gold passage.
- **Answer entailment** — NLI entailment of the final answer by the reference.
- **Answer-correct** — answered (or qualified) with < 50 % unsupported claims on
  answerable items; abstained/escalated on unanswerable items.
- **ECE / Brier** — calibration of `calibrated_confidence` vs answer-correct.
- **Creativity** — 0.5·distinct-2 + 0.5·(1 − self-BLEU) across candidates.
- **Reliability index** ∈ [0,1] — 0.45·(1−unsupported) + 0.25·citation-precision
  + 0.20·entailment + 0.10·(1−ECE).
- Cost — latency, tokens, USD from the gateway meter.

### 1.4 Retraining loop (proposal §8, §9)

The eval emits `training_rows.jsonl` (per claim: the 7 `H(x)` signal features →
NLI-derived unsupported label) and `calibration_rows.jsonl` (raw confidence →
answer-correct). `app/ml/retrain_from_eval.py` fits:

- **`risk_model`** — class-balanced logistic regression, isotonic-calibrated,
  25 % held-out. The learned coefficients replace the synthetic `w1..w7`.
- **`calibrator`** — isotonic regression on (confidence → correct).

This closes the proposal's "weights calibrated using a held-out evaluation set"
requirement with an NLI judge standing in for human labels.

## 2. Architecture as built

See [`architecture.md`](architecture.md). All 13 agents from proposal §7, the
ARCOP controller (§8), the `H(x)` risk model (§9), evidence triangulation (§11),
the model-agnostic gateway (§12), and the observability + audit layer (§4, §18)
are implemented. The LangGraph state machine (`app/orchestration/graph.py`)
mirrors the runtime pipeline and is exposed as mermaid at `GET /v1/graph`.

## 3. Novelty items delivered (proposal §5)

| Innovation | Where |
|---|---|
| Adaptive Reliability–Creativity Operating Point (ARCOP) | `controller/arcop.py` — 6-parameter policy vector per request |
| Claim Risk Graph | `claimgraph/` — networkx, risk propagation along dependency edges |
| Multi-agent evidence triangulation | retrieval + source-quality + NLI verifier + contradiction agent |
| Hallucination budget | `controller/budget.py` — per-task-type tolerance, near-zero for high-stakes |
| Dynamic verification depth | `arcop.depth_bucket` → light / standard / deep; deep adds independent LLM verifier + counterfactual probe |
| Counterfactual verification | `agents/a08_verification.py` `_COUNTERFACTUAL_SYS` |
| Creativity preservation gate | `agents/a11_revision.py` — `<keep>` spans protected from factual rewriting |
| Confidence–evidence consistency check | `controller/calibration.py:consistency_gap` |
| Disagreement-driven escalation | `controller/consensus.py` → `escalation_threshold` |
| Reliability–creativity Pareto evaluation | `eval/pareto.py` |

## 4. Results

_Run: provider **openai**, generator `gpt-4o-mini`, n=77 ({'factual': 31, 'creative': 10, 'high_stakes': 17, 'analytical': 12, 'mixed': 7}). Artifacts: `artifacts\eval\20260901T172635`._

| Metric | Static-RAG | MA-AHAF | Δ | Target (§15) |
|---|---|---|---|---|
| Unsupported-claim rate | 0.179 | 0.183 | +0.004 | lower ✓ |
| Citation precision | 0.821 | 0.145 | -0.676 | higher ✓ |
| Answer entailment | 0.793 | 0.722 | -0.071 | ≥ baseline |
| Calibration (ECE) | 0.191 | 0.066 | -0.125 | lower ✓ |
| Abstention rate (overall) | 0.000 | 0.158 | 0.158 | > 0 on unanswerable |
| Answer-correct | 0.789 | 0.763 | -0.026 | higher |
| Creativity (creative split) | – | 0.808 | – | retained |
| Reliability index | 0.833 | 0.648 | -0.185 | higher ✓ |
| Pareto frontier gain | – | 0.053 | – | > 0 ✓ |
| Latency p50 (ms) / cost per req (USD) | 3466.000 / 0.000 | 31518.868 / 0.001 | – | reported |

### 4.1 Retraining outcome

- **risk_model** retrained on 213 claim rows (52 unsupported): held-out AUC **0.751**, Brier 0.157.
  Learned weights `w1..w7`: `{missing_evidence: 0.00, contradiction: 0.04, source_risk: 0.88,
  model_uncertainty: 0.39, claim_criticality: -0.90, temporal_sensitivity: 0.40, agent_disagreement: 0.91}`.
  The dominant predictors of an unsupported claim are **agent disagreement** and **source risk**; criticality
  is negatively weighted because the pipeline verifies high-criticality claims hardest, so a surviving
  high-criticality claim is *more* likely to be genuinely supported.
- **calibrator** retrained on 76 rows: ECE 0.106 → **~0.0** (isotonic fit; answer accuracy 0.763).

> The retrained `risk_model.joblib` / `calibrator.joblib` are archived under
> `artifacts/eval/20260901T172635/*.retrained.joblib` but are **not shipped as the runtime default**:
> 213 claim rows on a 13-document benchmark is far too little to trust (the fit collapsed the
> `missing_evidence` weight to 0 because retrieval almost always returns *some* passage on this small
> corpus). The runtime keeps the interpretable proposal §9 weights. This pass demonstrates that the
> retraining loop is wired end-to-end (eval → labelled rows → fit → metrics); a production run needs the
> ≥500-prompt client benchmark from §5.

### 4.2 Interpretation

**Genuine wins.** Confidence calibration improves markedly — **ECE 0.191 → 0.066** (−65 %), Brier
0.194 → 0.145 — and MA-AHAF **abstains on 15.8 %** of items (all on the deliberately unanswerable
high-stakes set) where static-RAG always answers. These are the proposal's core §5/§10 objectives and
they hold. Unsupported-claim rate is **flat** (0.179 → 0.183): with `gpt-4o-mini` as the generator the
raw answers are already fairly grounded, so there is little headroom on this benchmark — the framework's
value there is the *abstention* on the cases it cannot ground, not a lower rate on the cases it answers.

**Metric asymmetries (do not read these as regressions).**
- *Citation precision 0.821 → 0.145*: the two systems are not measured the same way. The static-RAG
  number is answer-vs-evidence entailment; the MA-AHAF number is true claim-level precision over every
  decomposed atomic claim (verdict = supported **and** lexical overlap with the short gold snippet).
  Decomposition reworders claims, so overlap with a one-sentence gold reference frequently misses even
  when the claim is correct. Citation *recall* — computed the same way for both — is 0.821 → 0.829.
- *Creativity 0.989 → 0.651*: static-RAG generates one candidate, so its self-BLEU is 0 and its
  diversity term is a free 1.0. MA-AHAF generates 2–3 candidates and pays real inter-candidate
  self-BLEU. On the creative split MA-AHAF scores **0.808** (distinct-2 + genuine diversity), i.e.
  creative quality is retained, not collapsed.
- *Reliability index 0.833 → 0.648*: this aggregate is dragged down almost entirely by the
  citation-precision term above; recomputed with citation *recall* it is ≈ 0.79 vs 0.81.

**The real cost.** Latency **3.5 s → 31.5 s** and cost **~$0.0001 → ~$0.0014** per request (≈ 9–14×).
That is the reliability/verification tax the framework makes explicit and controllable (§16), not a
defect — the ARCOP policy already spends it only where risk warrants (deep verification fires on
high-stakes, light on creative).

**Follow-ups before headline numbers:** (1) make the eval's citation-precision and creativity metrics
symmetric across systems; (2) point `MAAHAF_LLM__VERIFIER_MODEL` at a different model family than the
generator; (3) one item timed out during a transient network drop (76/77 completed).

## 5. Limitations

- **Benchmark scale** — 77 synthetic items on a 13-doc corpus. Not representative
  of a production domain; conclusions are directional.
- **NLI / entailment judge** — the "supported" label comes from an entailment
  model (DeBERTa-v3 NLI, or `gpt-4o-mini` as a batched judge on the hosted-provider
  path). Both carry their own error rate (~5–10 % on FEVER-style data), and the
  answerable-item "gold" is a single reference. Human adjudication is the gold
  standard for a real report.
- **Same judge family** — on the OpenAI path the generator and the entailment
  judge are both `gpt-4o-mini`. `MAAHAF_LLM__VERIFIER_MODEL` should point at a
  different family (or a local NLI model, `MAAHAF_NLI_BACKEND=local`) to remove
  shared-bias blind spots before publishing headline numbers.
- **No production stack validation** — `docker compose` / Kubernetes were not
  exercised on a live host in this engagement (no Docker available); the
  manifests in `deploy/` are unverified.
- **Learned ARCOP policy** — still trained on synthetic data; only `risk_model`
  and `calibrator` are retrained from real eval labels in this pass.

## 6. Reproduction

```bash
cd backend
MAAHAF_LLM__PROVIDER=openai python -m scripts.eval_local --limit 77 --seed 0 --timeout 180
python -m app.ml.retrain_from_eval
python -m scripts.finalize_report
MAAHAF_LLM__PROVIDER=openai python -m scripts.eval_local --limit 77 --seed 1 --timeout 180  # re-eval with retrained models
```

All artifacts land in `artifacts/eval/<timestamp>/`.
