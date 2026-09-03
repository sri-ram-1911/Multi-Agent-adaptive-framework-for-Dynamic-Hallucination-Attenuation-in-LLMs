# MA-AHAF — Multi-Agent Adaptive Hallucination Attenuation Framework

> Automatic balancing between factual reliability and generative creativity.

MA-AHAF is a **model-agnostic adaptive intelligence layer** that sits between an
application and one or more LLMs. For every request it estimates hallucination
risk, evidence coverage, source agreement, claim criticality, ambiguity and
creativity demand, then selects a per-request **policy vector** controlling how
much grounding, verification, citation, uncertainty disclosure, creative latitude
and abstention are applied — with a full audit trail.

This repository is a **research-grade yet production-oriented prototype**
implementing the proposal `project proposal final.pdf`.

## What's inside

| Layer | Components |
|---|---|
| Input intelligence | Intent & Task Classifier, Risk Profiler |
| Adaptive control | ARCOP controller, policy engine, hallucination budget |
| Generation | Model-agnostic LLM gateway, candidate generator |
| Claim analysis | Claim decomposer, Claim Risk Graph |
| Evidence | Hybrid retriever (vector + BM25 + RRF + MMR), cross-encoder reranker, source-quality scorer |
| Verification | NLI entailment verifier, contradiction agent, consensus/conflict resolver |
| Response control | Revision agent, creativity-preservation gate, abstention/escalation gate |
| Observability | OpenTelemetry traces, Prometheus metrics, structured logs, audit store, React dashboard |
| Evaluation | Benchmark harness, reliability–creativity Pareto frontier, ablations |

All 13 agents from proposal §7 are implemented. ML/DL is used for embeddings,
reranking, NLI verification, intent classification, claim-type classification,
the hallucination risk model `H(x)`, source-quality scoring and confidence
calibration (see `docs/architecture.md`).

## Quickstart

```bash
cp .env.example .env            # set OPENAI_API_KEY
make up                         # docker compose: db (pgvector), redis, api, frontend
make bootstrap-models           # download HF models + train sklearn artifacts
make seed                       # load sample corpus + benchmark
make test                       # pytest (unit + integration)
```

### Run it without Docker or an API key

```bash
cd backend && pip install -e ".[dev]"
python -m scripts.demo --mock          # instant, deterministic, no downloads
python -m scripts.demo --real          # real ML/DL: bge-small + cross-encoder +
                                       #   DeBERTa-v3 NLI + local flan-t5 generator
                                       #   (first run downloads ~1.7 GB), no DB/API key
```

**Windows** (no `make`): use the bundled task runner —

```powershell
.\tasks.ps1 setup        # create venv + install deps
.\tasks.ps1 test
.\tasks.ps1 demo         # mock
.\tasks.ps1 demo-real    # local models, offline
.\tasks.ps1 up           # docker compose stack (needs Docker Desktop)
```

### See the dashboard (no Docker)

A standalone demo server runs the whole pipeline with an in-memory corpus — no
Postgres, no Redis, no API key. You only need **Node.js** for the UI.

```powershell
winget install OpenJS.NodeJS.LTS     # one time, if Node is missing
.\tasks.ps1 dashboard                # starts the demo API + the React dashboard
```

Then open **http://localhost:5173** — Playground, Traces, Trace Detail (claim
graph, agent timeline), Metrics, Evaluation, Knowledge Base. Or run the pieces
separately:

```powershell
.\tasks.ps1 serve                       # demo API on :8000  (add nothing = mock; `serve-real` = local models)
cd frontend; npm install; npm run dev   # dashboard on :5173
```

`--real` runs the full 13-agent pipeline against an in-memory corpus index
(`app/retrieval/local_store.py`) with genuine model inference for every step
except cloud generation.

- Dashboard: http://localhost:5173
- API docs (Swagger): http://localhost:8000/docs
- Metrics: http://localhost:8000/metrics
- Observability stack: `make up-obs` → Grafana http://localhost:3000

## Main endpoint

```bash
curl -s localhost:8000/v1/generate \
  -H 'x-api-key: dev-key' -H 'content-type: application/json' \
  -d '{"prompt": "What is the recommended daily water intake for adults?"}' | jq
```

Response contains `response`, `segments` (factual / assumption / creative),
`claims[]` with per-claim risk + verdict + evidence, `confidence`,
`calibrated_confidence`, `action` (answer / qualify / abstain / escalate),
`policy_vector`, and `trace_id`. `GET /v1/traces/{trace_id}` returns the full
per-agent trace.

## Evaluation

```bash
make eval    # runs MA-AHAF vs static-RAG baseline over data/benchmark/benchmark.jsonl
```

Produces `artifacts/eval/<run>/report.json` and `pareto.csv` (viewable in the
dashboard **Evaluation** page).

## Evaluation & retraining (no Docker needed)

```bash
cd backend
python -m scripts.eval_local --limit 40          # MA-AHAF vs static-RAG, local corpus
python -m app.ml.retrain_from_eval               # retrain risk_model + calibrator on the labels
python -m scripts.finalize_report                # fill docs/final-report.md §4
```

Set `MAAHAF_LLM__PROVIDER=openai` (with credits) for the GPT-4o-mini numbers.

## Documentation

- [`docs/SRS.md`](docs/SRS.md) — software requirements specification (FR-1…FR-22)
- [`docs/architecture.md`](docs/architecture.md) — layers, flow, ML/DL details
- [`docs/evaluation-methodology.md`](docs/evaluation-methodology.md) — benchmark & metrics
- [`docs/final-report.md`](docs/final-report.md) — methodology, results, limitations (proposal §13)
- [`SECURITY.md`](SECURITY.md) — controls + go-live checklist
- [`deploy/k8s/`](deploy/k8s/) — production Kubernetes manifests · [`deploy/loadtest/`](deploy/loadtest/) — k6 load test

## License

Proprietary — Confidential prototype. See proposal IP terms.
