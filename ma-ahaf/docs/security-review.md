# Security Review — MA-AHAF

Internal review of the codebase against the OWASP ASVS / API Top-10 and proposal
§18. Scope: `backend/app/**`, `deploy/**`, `frontend/src/api/**`. Date: 2026-09-01.

> A third-party penetration test is still required before go-live (see
> `SECURITY.md`). This review covers code-level issues only.

## Method

Manual review of auth, tenancy, input handling, SQL, secrets, logging, SSRF,
dependencies, and the deployment manifests. `pip-audit` / `npm audit` / Trivy are
wired into CI (`.github/workflows/ci.yml`).

## Findings

| ID | Severity | Finding | Status |
|----|----------|---------|--------|
| S-1 | Medium | Demo server (`scripts/serve_demo.py`) has no auth and bound `0.0.0.0` | **Fixed** — binds `127.0.0.1`; docstring warns it is dev-only |
| S-2 | Medium | Gateway logged the full LLM completion on JSON-parse failure (may contain user prompt / evidence / PII) | **Fixed** — logs an 80-char structural preview + length only |
| S-3 | Low | `dev-api-key` compared with `==` (timing side-channel) | **Fixed** — `secrets.compare_digest`, and disabled entirely when `MAAHAF_ENV=prod` |
| S-4 | Low | Rate limiter raised an uncaught exception if Redis was down (self-DoS) | **Fixed** — fails open with a warning + `maahaf_rate_limiter_errors_total` metric; `_FAIL_OPEN=False` to fail closed |
| S-5 | Low | Weak default `JWT_SECRET` / `dev-key` could reach production silently | **Fixed** — `Settings.validate_for_runtime()`; startup **aborts** in prod on weak secrets, `dev-key`, `provider=mock`, or `localhost` DB URL |
| S-6 | Low | CORS allowed `*` in every environment | **Fixed** — `["*"]` only when `MAAHAF_ENV=dev`; allow-list from `MAAHAF_CORS_ORIGINS` otherwise; methods/headers narrowed |
| S-7 | Info | `/v1/admin/token` minted JWTs with no auth | **Fixed** — returns 403 in prod; wire OIDC/SSO exchange instead |
| S-8 | Info | Prompt-injection via retrieved documents | **Documented** (`SECURITY.md`); external retrieval off by default, KB is tenant-scoped; a dedicated injection classifier is recommended for untrusted corpora |
| S-9 | Info | No per-tenant token/cost budget (only per-request revision cap + rate limit) | **Open** — recommended for prod; add a daily token ceiling per tenant |
| S-10 | Info | Frontend bundle 802 KB, no code-splitting | **Open** — cosmetic; lazy-load `reactflow`/`recharts` |

## Verified OK

- **Tenancy** — every DB read/write is scoped by `principal.tenant_id`
  (`db/repositories.py`, all routers, `routes_review.py`, `routes_metrics.py`).
  No cross-tenant read path found.
- **SQL injection** — the two raw-SQL spots (`retrieval/vector_store.py`,
  `retrieval/keyword.py`) use bound parameters; `_vec_literal` only ever formats
  floats. Everything else is SQLAlchemy Core/ORM.
- **Secrets in VCS** — `.env`, `backend/.env` are git-ignored;
  `.env.example` carries placeholders only. `api_keys` stored as SHA-256 hashes,
  raw key shown once. OpenAI key read from env, never logged.
- **AuthN/Z** — JWT via `python-jose` with explicit algorithm allow-list; RBAC
  rank check on every protected route (`requires(...)`).
- **PII** — `redact_pii()` runs before any prompt/context is persisted or sent
  through the pipeline; matched types recorded on the request + audit trace.
- **SSRF** — no user-controlled URLs are fetched. Retrieval is DB/corpus only;
  `MAAHAF_ALLOW_EXTERNAL_RETRIEVAL` gates any future web retriever. The k8s
  NetworkPolicy restricts egress to Postgres/Redis/OTel/:443/DNS.
- **Container** — `deploy/k8s/api.yaml`: non-root, read-only rootfs, all caps
  dropped, no privilege escalation.
- **Audit integrity** — every response's trace pins `model_versions`; human
  review decisions are appended to the trace, not overwritten.

## Recommendations (prioritised)

1. Third-party pen test + DAST against a staging deployment.
2. Per-tenant daily token/cost budget (S-9).
3. Secret manager integration (Vault Agent / External Secrets) — never a raw k8s `Secret`.
4. Add `bandit` to CI for Python-specific static analysis.
5. Sign images (cosign) + admission policy (Kyverno) blocking unsigned images.
6. Structured audit-log export to a SIEM with alerts on: repeated auth failures,
   rate-limiter errors, config-invalid startup events, escalation spikes.
