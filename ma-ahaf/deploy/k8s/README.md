# Kubernetes deployment

> **Status: reference manifests, not yet applied to a live cluster.** They encode
> the intended production topology (proposal §18). Validate with
> `kubectl apply --dry-run=server -f deploy/k8s/` before a real rollout.

## Topology

```
Internet ──TLS──> nginx-ingress ──/──> maahaf-frontend (2 replicas, static)
                               └──/v1 /health /metrics──> maahaf-api (3-20 replicas, HPA)
                                                             ├──> Postgres (managed / StatefulSet, pgvector)
                                                             ├──> Redis
                                                             └──> OTel collector (observability ns)
```

## Apply order

```bash
kubectl apply -f namespace.yaml
kubectl apply -f config.yaml
# create the secret from your secret manager — do NOT use secrets.example.yaml literally
kubectl apply -f postgres.yaml          # or skip and use managed Postgres
kubectl apply -f api.yaml               # runs `alembic upgrade head` as an initContainer
kubectl apply -f frontend-ingress.yaml
```

## Hardening baked in

- `runAsNonRoot`, `readOnlyRootFilesystem`, all capabilities dropped, no privilege escalation
- HPA (CPU 70%, 3→20), PodDisruptionBudget (minAvailable 2), rolling update maxUnavailable 0
- NetworkPolicy egress allow-list (Postgres, Redis, OTel, :443, DNS only)
- TLS via cert-manager; ingress rate-limit + ModSecurity annotations
- Migrations run once per rollout as an initContainer

## Still required for go-live

- Secret manager integration (Vault Agent / External Secrets) — `secrets.example.yaml` shows the shape
- Managed Postgres with automated backups + PITR, `CREATE EXTENSION vector`
- Image signing (cosign) + admission policy (Kyverno/Gatekeeper)
- Log shipping + alerting rules (see `../../observability/`)
- DR runbook, on-call rotation
