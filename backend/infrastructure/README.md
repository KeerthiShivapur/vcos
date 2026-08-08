# VCOS Infrastructure & Enterprise Reliability (Phase 16)

Platform-wide cloud infrastructure manifests for the VCOS global platform.
These are the deployment artifacts for the Phase 16 API surface
(`/api/v1/infrastructure/**`) and its services (`backend/app/infrastructure/`).

## Layout

| Directory | Manifests | Backs Phase 16 surface |
|---|---|---|
| `docker/` | Image build + local compose (api, worker, nginx LB) | docker healthchecks |
| `kubernetes/` | Namespace, api/worker deployments, ingress | deployment endpoints |
| `terraform/` | Global VPC + EKS + RDS + ElastiCache + OpenSearch + S3 | regions service |
| `helm/` | Charts for api/worker | deployment strategy |
| `ansible/` | Bare-metal / AMI provisioning + hardening | cluster service |
| `monitoring/` | Prometheus, rules, Alertmanager, Grafana | health metrics, alerts |
| `logging/` | Loki + Fluent Bit | audit + event stream |
| `tracing/` | Tempo + OTel collector | distributed traces |
| `backups/` | CronJob, scripts, PITR config (14-day window) | backups service (PITR) |
| `disaster_recovery/` | Playbook, failover, RPO 15m / RTO 30m | DR service, RPO/RTO |
| `networking/` | VPC peering + routing | region interconnect |
| `security/` | NetworkPolicy, secret rotation, pod hardening | RBAC + secrets |
| `cdn/` | CloudFront distribution + cache policy | CDN endpoints |
| `load_balancer/` | nginx.conf (docker), Gateway API routes | nearest-region routing |
| `ai_cluster/` | GPU node pool + model gateway + AI guardrails | AI inference cluster |
| `database_cluster/` | CNPG Postgres HA + partitioning | cluster topology, replicas |
| `graph_cluster/` | Neo4j causal cluster | org graph cluster |
| `redis_cluster/` | Redis Cluster + Sentinel | cache cluster |
| `object_storage/` | MinIO distributed + lifecycle | object storage tier |
| `search_cluster/` | OpenSearch + ILM | search cluster |
| `deployment/` | Argo Rollouts canary/blue-green + rollback | deployment strategies |
| `feature_flags/` | Flags service + entitlements | entitlement gates |
| `compliance/` | SOC2/ISO27001/GDPR evidence + drills | compliance reports |
| `autoscaling/` | HPA + platform guardrails | autoscaling service (70/30) |
| `secrets/` | (see `security/secret-rotation.yaml`) | Vault-backed rotation |
| `observability/` | Unified metrics/logs/traces + SLOs | reliability SLOs |

## Key platform contracts (mirrored by services in `backend/app/infrastructure/`)

- **RPO 15m / RTO 30m** — `disaster_recovery/rpo-rto.yaml`, enforced by `disaster_recovery_service`.
- **PITR 14-day window** — `backups/pitr-config.yaml`, surfaced at `GET /infrastructure/backups/pitr`.
- **Scale-out at 70%, scale-in at 30%, MIN 1 / MAX 20** — `autoscaling/autoscaling-hpa.yaml`, `autoscaling_service`.
- **Strategies** — `deployment/rollout.yaml`: `rolling`, `blue_green`, `canary` (10% -> 50% -> 100%).
- **Region status** — `active`, `degraded`, `maintenance` map to `healthy`/`degraded` region health.

## Apply order (production)

1. `terraform apply` (networking, VPC)
2. `kubectl apply -f kubernetes/namespace.yaml`
3. `kubectl apply -f database_cluster/ redis_cluster/ graph_cluster/ search_cluster/ object_storage/`
4. `kubectl apply -f monitoring/ logging/ tracing/ observability/`
5. `kubectl apply -f backups/ disaster_recovery/ deployment/`
6. `helm upgrade --install vcos ./helm`
