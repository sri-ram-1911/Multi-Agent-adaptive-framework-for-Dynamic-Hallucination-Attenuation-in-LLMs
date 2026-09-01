# MA-AHAF Architecture

## 1. Position in the stack

MA-AHAF is an **adaptive orchestration layer** between an application and one or
more LLMs (proposal §3). The application calls `POST /v1/generate`; MA-AHAF
returns a controlled response plus evidence, per-claim risk, calibrated
confidence, a policy vector and a full audit trace.

## 2. Request flow (proposal §6)

```
POST /v1/generate
  │
  ▼
Intent & Task Classifier ──► Risk Profiler ──► Policy Controller (ARCOP)
  │                                                   │  policy vector π
  ▼                                                   ▼
Candidate Generator (N candidates, temp/system from π)
  │
  ▼
Claim Decomposer ──► Claim Risk Graph (claims ↔ entities ↔ evidence ↔ deps)
  │
  ▼
Evidence Retrieval (hybrid: vector + BM25 + RRF + MMR + cross-encoder rerank,
                    query expansion, contradictory-evidence retrieval, Redis cache)
  │
  ▼
Source Quality Agent (ML scorer) ──► source agreement signal
  │
  ▼
Verification Agent (NLI entailment; + independent LLM verifier at depth ≥ 1;
                    + counterfactual probe at depth 2 for critical claims)
Contradiction Agent (NLI contradiction over evidence + internal consistency)
  │
  ▼
Hallucination Risk Model  H(x) per claim  ──►  risk propagation along dep graph
  │
  ▼
Creativity Agent (distinct-n, self-BLEU diversity, embedding novelty)
  │
  ├── needs revision?  ──► Revision Agent (creativity-preservation gate) ──┐
  │                                                                        │ (bounded loop,
  ▼                                                                        │  MAAHAF_MAX_REVISION_LOOPS)
Consensus / Conflict Resolver ◄──────────────────────────────────────────────┘
  │
  ▼
Abstention / Escalation Agent  →  answer | qualify | abstain | escalate
  │
  ▼
Finalize (segment into factual / assumption / creative) ──► Audit Agent ──► persist
```

The canonical graph is defined in [`app/orchestration/graph.py`](../backend/app/orchestration/graph.py)
(LangGraph `StateGraph`, available as a mermaid diagram at `GET /v1/graph`). The
runtime executes the same nodes through an explicit loop in
[`app/orchestration/pipeline.py`](../backend/app/orchestration/pipeline.py).

## 3. The 13 agents (proposal §7)

| # | Agent | Module | Key output |
|---|-------|--------|-----------|
| 1 | Intent & Task Classifier | `agents/a01_intent_classifier.py` | task profile, ambiguity |
| 2 | Risk Profiler | `agents/a02_risk_profiler.py` | request risk score + factors |
| 3 | Policy Controller (ARCOP) | `agents/a03_policy_controller.py` | policy vector |
| 4 | Candidate Generator | `agents/a04_candidate_generator.py` | N candidates |
| 5 | Claim Decomposer | `agents/a05_claim_decomposer.py` | claim graph |
| 6 | Evidence Retrieval | `agents/a06_evidence_retrieval.py` | evidence set + coverage |
| 7 | Source Quality | `agents/a07_source_quality.py` | source scores, agreement |
| 8 | Verification | `agents/a08_verification.py` | per-claim verdicts |
| 9 | Contradiction | `agents/a09_contradiction.py` | conflict report |
| 10 | Creativity | `agents/a10_creativity.py` | creativity score, spans |
| 11 | Revision | `agents/a11_revision.py` | revised draft |
| 12 | Abstention / Escalation | `agents/a12_abstention.py` | safety action |
| 13 | Audit | `agents/a13_audit.py` | trace record |

## 4. Adaptive Reliability–Creativity Controller (proposal §8)

`app/controller/arcop.py` computes the policy vector

```
π = f(risk, intent, evidence_coverage, claim_criticality, ambiguity,
      source_agreement, creativity_demand, model_confidence, cost, latency)
```

with parameters **grounding_intensity, verification_depth, creativity_allowance,
citation_requirement, abstention_threshold, escalation_threshold**. The default
is an interpretable rule/scoring engine. If `app/ml/artifacts/policy.joblib`
exists (a `MultiOutputRegressor` trained by `app/ml/train_policy.py`) it is
blended 50/50 with the rules, then **re-clamped to the rule engine's safety
floor** for verification / citation / abstention on risky requests, so a poor
learned policy can never disable safety behaviour. Tenant profiles
(`strict | balanced | creative`) and caller `policy_overrides` (bounded ≤ 0.3
loosening) adjust the vector.

## 5. Hallucination risk model (proposal §9)

`app/controller/risk_model.py` — the proposal's formula

```
H(x) = w1(1-EvidenceCoverage) + w2·Contradiction + w3·SourceRisk
     + w4·ModelUncertainty + w5·ClaimCriticality + w6·TemporalSensitivity
     + w7·AgentDisagreement
```

implemented as a **calibrated logistic model** (isotonic-calibrated) whose
coefficients are the learned `w1..w7` (`app/ml/train_risk_model.py`). Every score
returns `risk_contributions` = normalised `coef·feature`, i.e. an explanation of
*why* the claim is high risk. Risk then propagates along the Claim Risk Graph
dependency edges (`app/claimgraph/graph.py`).

## 6. ML / DL inventory

| Component | Type | Model / method | Fallback (offline) |
|---|---|---|---|
| Embeddings | DL | `BAAI/bge-small-en-v1.5` | hashed bag-of-tokens (384-d) |
| Reranker | DL | `cross-encoder/ms-marco-MiniLM-L-6-v2` | lexical overlap |
| Verification / contradiction | DL | `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` NLI | overlap + negation heuristic |
| Intent classifier | DL | zero-shot `facebook/bart-large-mnli`; opt. fine-tuned DistilBERT | keyword scoring |
| Claim-type classifier | ML | TF-IDF + LogisticRegression | LLM-provided type |
| Hallucination risk `H(x)` | ML | isotonic-calibrated LogisticRegression | proposal's fixed weights |
| Source-quality scorer | ML | GradientBoostingRegressor | weighted sum |
| Confidence calibration | ML | IsotonicRegression + ECE | power-law shrink |
| ARCOP policy (learning-to-route) | ML | MultiOutput GradientBoosting | rule engine |
| Creativity scoring | DL/ML | embedding novelty + distinct-n + self-BLEU | distinct-n only |
| LLM generation / verification / revision | LLM | OpenAI (`gpt-4o` / `gpt-4o-mini` by role) via gateway | deterministic `MockAdapter` |

`make bootstrap-models` downloads the HF models and trains the sklearn artifacts
(synthetic-seeded via `app/ml/synth_data.py`; retrain on client eval logs).

## 7. Model-agnostic LLM gateway (proposal §12)

`app/llm/gateway.py` maps a **role** (`generator | verifier | decomposer |
reviser | judge | expander`) to a model + adapter. Adapters: `openai_adapter`
(chat + logprob uncertainty), `local_adapter` (any OpenAI-compatible endpoint —
Ollama/vLLM, used for verifier diversity), `mock_adapter`. The gateway adds
retry/backoff, a `UsageMeter` (tokens + USD via `price_table`), and Prometheus
counters.

## 8. Data model

`app/db/models.py` (PostgreSQL + pgvector): `tenants`, `api_keys`, `documents`,
`chunks` (HNSW vector index + GIN tsvector), `requests`, `claims`, `agent_runs`,
`audit_traces`, `eval_runs`, `escalation_queue`. Every table with tenant data
carries `tenant_id` and all queries are row-scoped (proposal §18 tenant
isolation).

## 9. Observability (proposal §4, §18)

- **Tracing** — OpenTelemetry spans per agent → OTLP collector.
- **Metrics** — Prometheus (`/metrics`): request/agent latency histograms, tokens
  & cost counters, verification-depth histogram, abstention counter, agent
  disagreement gauge, max-claim-risk histogram. Grafana dashboard provisioned.
- **Structured logs** — structlog JSON.
- **Audit store** — full per-request trace with agent votes and pinned model
  versions for reproducibility.

## 10. Security (proposal §18)

API-key + JWT auth, RBAC (`viewer < operator < admin`), tenant row-scoping,
per-key Redis rate limiting, PII redaction before persistence
(`app/core/security.py`), secrets via env only, `MAAHAF_ALLOW_EXTERNAL_RETRIEVAL`
flag, audit trail + escalation queue for high-risk responses.
