# Multi-Region Active-Active Infrastructure for VCOS

Production-ready multi-region infrastructure deployment for VCOS across 3 AWS regions.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Cloudflare Global Load Balancer                      │
│                    (Geo-routing, DDoS protection, WAF)                       │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────┐           ┌───────────────┐           ┌───────────────┐
│   US East 1   │           │   EU West 1   │           │  AP SE 1      │
│  (Primary)    │           │  (Secondary)  │           │  (Secondary)  │
├───────────────┤           ├───────────────┤           ├───────────────┤
│ EKS (3 nodes) │           │ EKS (2 nodes) │           │ EKS (2 nodes) │
│ RDS (Multi-AZ)│           │ RDS (Multi-AZ)│           │ RDS (Multi-AZ)│
│ ElastiCache(3)│           │ ElastiCache(2)│           │ ElastiCache(2)│
│ S3 (Primary)  │           │ S3 (Replica)  │           │ S3 (Replica)  │
│ LiveKit (3)   │◄──────────►│ LiveKit (2)   │◄──────────►│ LiveKit (2)   │
│ Egress (2)    │           │ Ingress (2)   │           │ Recorder (2)  │
└───────────────┘           └───────────────┘           └───────────────┘
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    ▼
                    ┌─────────────────────────────┐
                    │   Cross-Region Replication  │
                    │  • PostgreSQL Async Replica │
                    │  • Redis Cross-Region Sync  │
                    │  • S3 Cross-Region Replica  │
                    │  • LiveKit Recording Sync   │
                    └─────────────────────────────┘
```

## Components

| Component | Primary (us-east-1) | Secondary (eu-west-1) | Secondary (ap-southeast-1) |
|-----------|---------------------|-----------------------|----------------------------|
| **EKS Cluster** | 3 nodes (m6i.xlarge) | 2 nodes (m6i.xlarge) | 2 nodes (m6i.xlarge) |
| **RDS PostgreSQL** | db.r6g.xlarge Multi-AZ | db.r6g.xlarge Multi-AZ | db.r6g.large Multi-AZ |
| **ElastiCache Redis** | cache.r6g.xlarge (3 nodes) | cache.r6g.xlarge (2 nodes) | cache.r6g.large (2 nodes) |
| **S3 Buckets** | Primary (CRR enabled) | Cross-region replica | Cross-region replica |
| **LiveKit Servers** | 3 replicas | 2 replicas | 2 replicas |
| **LiveKit Egress** | 2 replicas | - | - |
| **LiveKit Ingress** | 2 replicas | - | - |
| **LiveKit Recorder** | 2 replicas | - | - |

## Quick Start

### Prerequisites

- AWS CLI configured with appropriate permissions
- Terraform >= 1.6.0
- kubectl >= 1.28
- helm >= 3.12
- AWS credentials with admin permissions
- Cloudflare API token
- Domain `vcos.io` in Cloudflare

### Required Secrets (GitHub/Environment)

```bash
# AWS
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY

# Database
POSTGRES_PASSWORD
REDIS_PASSWORD

# LiveKit
LIVEKIT_API_KEY
LIVEKIT_API_SECRET
TURN_PASSWORD
TURN_SECRET

# Cloudflare
CLOUDFLARE_API_TOKEN
CLOUDFLARE_ZONE_ID

# AWS Keys for S3
AWS_ACCESS_KEY
AWS_SECRET_KEY

# LiveKit
TURN_PASSWORD
TURN_SECRET
SRT_PASSPHRASE

# Notifications
SLACK_WEBHOOK_URL
PAGERDUTY_SERVICE_KEY
```

### Quick Deploy

```bash
# 1. Initialize Terraform
cd infra/multi-region/terraform
terraform init

# 2. Plan all regions
terraform plan -out=tfplan.all.out

# 2. Apply (requires approval)
terraform apply tfplan.all.out
```

Or use GitHub Actions:
```bash
# Trigger via GitHub Actions
gh workflow run deploy-multi-region.yml -f region=all -f environment=production
```

## Deployment Order

1. **VPC & Networking** (per region)
2. **RDS PostgreSQL** (Multi-AZ, encrypted)
3. **ElastiCache Redis** (Multi-AZ, encrypted)
4. **EKS Clusters** (with IRSA, add-ons)
4. **S3 Buckets** (with Cross-Region Replication)
5. **EKS Add-ons** (CNI, CSI, Cert Manager, External DNS, etc.)
6. **LiveKit Helm Chart** (Recording, Ingress, Egress)
7. **Monitoring Stack** (Prometheus, Grafana, ServiceMonitors)
8. **Cloudflare DNS/Load Balancer** (Global LB, Geo-routing)
8. **Autoscaling** (HPA for all components)

## Key Features Implemented

### High Availability
- ✅ Multi-AZ RDS (synchronous replication)
- ✅ ElastiCache Multi-AZ with auto-failover
- ✅ EKS Multi-AZ node groups
- ✅ Cross-region S3 replication (CRR)
- ✅ PostgreSQL async cross-region replication
- ✅ Redis cross-region replication

### Global Load Balancing
- ✅ Cloudflare Load Balancer with geo-routing
- ✅ Latency-based routing
- ✅ Health checks per region
- ✅ Automatic failover

### Auto-scaling
- ✅ EKS Cluster Autoscaler
- ✅ HPA for LiveKit (CPU, memory, connections)
- ✅ HPA for Egress (queue depth)
- ✅ HPA for Ingress (active sessions)
- ✅ HPA for Recorder (active recordings)

### Monitoring & Alerting
- ✅ Prometheus + Grafana per region
- ✅ 30+ Prometheus alerting rules
- ✅ SLO tracking (connection success, latency, egress success)
- ✅ Alertmanager with PagerDuty/Slack
- ✅ SLO dashboards

### Security
- ✅ IRSA for all service accounts
- ✅ KMS encryption (EKS, RDS, S3, EBS)
- ✅ VPC endpoints for all AWS services
- ✅ Private subnets for all workloads
- ✅ WAF rules (SQLi, XSS, rate limiting)
- ✅ Cloudflare WAF + Rate limiting
- ✅ mTLS between services

## Testing

### Chaos Engineering
```bash
# Run chaos experiments
./scripts/chaos-engineering.sh all
```

### Load Testing
```bash
# Run load tests
./scripts/load-test.sh all
```

## Verification Checklist

After deployment, verify:

- [ ] All EKS clusters healthy (3/3 nodes Ready)
- [ ] LiveKit pods running (3/3 in us-east-1, 2/2 others)
- [ ] RDS instances available (Multi-AZ)
- [ ] ElastiCache clusters available
- [ ] S3 cross-region replication working
- [ ] LiveKit Egress/Ingress/Recorder pods running
- [ ] Prometheus scraping all targets
- [ ] Grafana dashboards showing data
- [ ] Alertmanager firing test alerts
- [ ] Cloudflare DNS resolving correctly
- [ ] Global load balancer health checks passing
- [ ] Cross-region replication lag < 10s

## Disaster Recovery

- **RPO**: 5 minutes (async replication)
- **RTO**: 15 minutes (automated failover)
- **Backup**: Daily at 2 AM UTC, 90-day retention
- **DR Regions**: us-east-1 (primary) → eu-west-1 → ap-southeast-1
- **Failover Test**: Monthly automated

## Cost Optimization

- **Savings Plans**: 80% coverage target
- **Reserved Instances**: 70% coverage
- **Spot Instances**: 30% max for batch workloads
- **S3 Intelligent Tiering**: Enabled
- **Lifecycle Policies**: 30d → IA, 90d → Glacier, 365d → Deep Archive

## Support

- **Docs**: https://docs.vcos.io/infra/multi-region
- **Issues**: https://github.com/vcos/infra/issues
- **Slack**: #infra-multi-region
- **On-call**: PagerDuty rotation