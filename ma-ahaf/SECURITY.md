# Security

## Reporting

Email security@your-org.example with details and a PoC. We aim to acknowledge
within 2 business days. Do not open public issues for vulnerabilities.

## Controls implemented (proposal §18)

| Control | Where |
|---|---|
| API-key + JWT auth, RBAC (viewer < operator < admin) | `app/api/deps.py`, `app/core/security.py` |
| Tenant isolation (row-scoping on `tenant_id`, every query) | `app/db/repositories.py`, all routes |
| Per-key token-bucket rate limiting | `app/core/ratelimit.py` |
| PII redaction before any prompt/response/evidence is persisted | `app/core/security.py:redact_pii` |
| Secrets via environment only; **startup refuses weak prod config** | `app/config.py:validate_for_runtime`, `app/main.py` lifespan |
| `dev-api-key` and `/v1/admin/token` disabled when `MAAHAF_ENV=prod` | `app/api/deps.py`, `app/api/routes_admin.py` |
| CORS locked to an allow-list outside `dev` | `app/config.py:cors_origin_list` |
| External-retrieval kill switch | `MAAHAF_ALLOW_EXTERNAL_RETRIEVAL` |
| Model/version pinning in every audit trace | `app/agents/a13_audit.py`, `audit_traces.model_versions` |
| Container: non-root, read-only rootfs, caps dropped | `deploy/k8s/api.yaml` |
| Egress allow-list (Postgres, Redis, OTel, :443, DNS) | `deploy/k8s/frontend-ingress.yaml` NetworkPolicy |
| Encryption in transit (TLS at ingress via cert-manager) | `deploy/k8s/frontend-ingress.yaml` |

## Required before production go-live

- [ ] Secret manager (Vault Agent Injector / External Secrets Operator) — never a raw `Secret`
- [ ] Rotate any key that has touched a working tree or chat/shell history
- [ ] Managed Postgres with encryption at rest + automated backups + PITR
- [ ] Application-level field encryption for stored prompts if the data class requires it
- [ ] Third-party penetration test + dependency scanning in CI (`pip-audit`, `npm audit`, Trivy on images)
- [ ] Image signing (cosign) + admission control (Kyverno)
- [ ] WAF / bot protection at the edge
- [ ] SIEM log shipping + alerting on: auth failures, rate-limit hits, escalations, config-invalid events
- [ ] Data retention job honouring `tenants.retention_days` (cron)
- [ ] DPA / sub-processor list if handling EU personal data (proposal §18, GDPR)

## Threat notes

- **Prompt injection via retrieved documents** — the KB is tenant-scoped and
  external retrieval is off by default; verification agents treat evidence as
  data, not instructions, but a dedicated injection classifier is a recommended
  addition for untrusted corpora.
- **LLM cost abuse** — rate limiting + `MAAHAF_MAX_REVISION_LOOPS` cap per-request
  spend; add a per-tenant daily token budget for hard limits.
- **Verifier collusion** — set `MAAHAF_LLM__VERIFIER_MODEL` to a different family
  than the generator (or point it at a local model) to reduce shared-bias misses.
