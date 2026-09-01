# MA-AHAF — Software Requirements Specification (prototype)

Derived from `project proposal final.pdf` (§4 objectives, §15 success criteria,
§17 deliverables, §18 governance).

## 1. Scope

A model-agnostic adaptive layer that, per request, determines how factual, how
creative, how strongly grounded and how aggressively verified a response should
be, while maintaining a transparent audit trail.

## 2. Functional requirements

| ID | Requirement | Where |
|----|-------------|-------|
| FR-1 | Classify each request (factual/analytical/creative/mixed/high-stakes) and estimate ambiguity | `agents/a01` |
| FR-2 | Produce a request risk score from consequence, domain, ambiguity, numeric load | `agents/a02` |
| FR-3 | Compute a per-request policy vector (6 parameters) adaptively | `controller/arcop.py` |
| FR-4 | Generate ≥1 candidate response constrained by the policy vector | `agents/a04` |
| FR-5 | Decompose a response into atomic claims with type + criticality + entities | `agents/a05` |
| FR-6 | Hybrid retrieval (dense + lexical), query expansion, contradictory-evidence retrieval, caching | `retrieval/` |
| FR-7 | Score source authority/freshness/relevance/consistency/corroboration | `agents/a07` |
| FR-8 | Verify each claim against evidence (NLI + independent LLM verifier + counterfactual at depth) | `agents/a08` |
| FR-9 | Detect contradicting evidence and internal inconsistency | `agents/a09` |
| FR-10 | Assess creativity (novelty, diversity) and preserve explicitly creative spans | `agents/a10`, `agents/a11` |
| FR-11 | Compute claim-level `H(x)` with explanation; propagate on the claim graph | `controller/risk_model.py` |
| FR-12 | Enforce a task-specific hallucination budget | `controller/budget.py` |
| FR-13 | Calibrate confidence; flag confidence–evidence inconsistency | `controller/calibration.py` |
| FR-14 | Decide answer / qualify / abstain / escalate from calibrated confidence, risk, disagreement, thresholds | `agents/a12` |
| FR-15 | Segment the final answer into factual / assumption / creative | `agents/a12`, `orchestration/nodes.py` |
| FR-16 | Record a full audit trace with agent votes + pinned model versions | `agents/a13` |
| FR-17 | REST API with OpenAPI docs; KB ingest/search; trace & metrics retrieval; eval trigger | `api/` |
| FR-18 | Evaluation harness: MA-AHAF vs static-RAG baseline + Pareto frontier | `eval/` |
| FR-19 | Model-agnostic gateway: swap models per role without code changes | `llm/gateway.py` |
| FR-20 | Configurable policy profiles per tenant; bounded caller overrides | `controller/arcop.py`, `api/routes_admin.py` |

## 3. Non-functional requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | Tenant isolation by row-scoping on `tenant_id` for all data access |
| NFR-2 | Auth: API key + JWT; RBAC roles viewer/operator/admin |
| NFR-3 | PII redaction before any prompt/response/evidence is persisted |
| NFR-4 | Secrets supplied only via environment; none in source |
| NFR-5 | Encryption in transit (TLS at ingress) and at rest (DB volume); field-level app encryption is a documented extension |
| NFR-6 | OpenTelemetry traces + Prometheus metrics + structured JSON logs |
| NFR-7 | Model/version traceability for every response |
| NFR-8 | Config flag to disable external retrieval |
| NFR-9 | Bounded revision loop (`MAAHAF_MAX_REVISION_LOOPS`) to cap latency/cost |
| NFR-10 | Deterministic offline mode (`MAAHAF_LLM__PROVIDER=mock`) for CI and air-gapped eval |
| NFR-11 | Reproducible evaluation over fixed benchmark splits |

## 4. Acceptance criteria (proposal §15)

- Lower unsupported-factual-claim rate than the static-RAG baseline on factual/
  high-stakes splits.
- Improved evidence/claim alignment and citation precision on factual tasks.
- Improved calibration (lower ECE) and appropriate abstention on unanswerable
  items (`labels.answerable == false`).
- Creative quality retained on the creative split (distinct-2 / diversity not
  materially reduced).
- Demonstrable movement of the reliability–creativity Pareto frontier
  (`pareto_frontier_gain > 0`).
- End-to-end API response carries traceable agent decisions + configurable policy
  controls.
- Operational visibility into latency, token usage, verification depth, failure
  modes.

## 5. Out of scope for the prototype (proposal §20 future extensions)

Learned-from-production routing controller; multimodal verification; live web
freshness monitoring; per-user personalised policies; Kubernetes production
manifests; full enterprise DLP; human-review queue UI (escalations are recorded;
the queue endpoint exists, the reviewer UI is a stub).
