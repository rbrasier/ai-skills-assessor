# ADR-006: Deployment Platform (Railway → AWS Migration Path)

## Status
Accepted

## Date
2026-04-20

## Context

Phase 3 requires deploying the voice engine (Python/FastAPI/Pipecat), web frontend (Next.js), and PostgreSQL database (with pgvector) to a cloud environment in the Asia-Pacific region.

The original Phase 3 document assumed AWS or Azure in `ap-southeast-2` (Sydney). However, for an early-stage project with no compliance requirements yet, the operational overhead of AWS/Azure (VPC, IAM roles, ECS, ECR, RDS, load balancers) is disproportionate to current needs. A simpler PaaS option should be evaluated.

Key constraints:
1. **Latency**: Daily.co (telephony/WebRTC) has its primary PSTN gateway for Australian +61 numbers in `ap-southeast-2` (Sydney). ADR-004 targeted sub-500ms end-to-end voice latency.
2. **pgvector**: PostgreSQL must support the pgvector extension (required by ADR-005).
3. **Docker**: Both services run as Docker containers.
4. **Secrets**: No credentials in source control.
5. **HTTPS**: All endpoints must be TLS-terminated.

## Options Considered

| Dimension | Railway (Singapore) | AWS (Sydney) | Azure (Sydney) |
|---|---|---|---|
| Region | `asia-southeast1` | `ap-southeast-2` | `australiaeast` |
| Setup time | Hours | Days–weeks | Days–weeks |
| Monthly cost (MVP) | ~$20–60 | ~$200–500 | ~$200–500 |
| pgvector | ✅ | ✅ (RDS) | ✅ (Flexible Server) |
| HTTPS | ✅ Automatic | ✅ ACM | ✅ App Gateway |
| Secrets | ✅ Env vars (encrypted) | ✅ Secrets Manager | ✅ Key Vault |
| CI/CD | ✅ Auto-deploy from GitHub | GitHub Actions → ECR → ECS | GitHub Actions → ACR → Container Apps |
| Monitoring | ⚠️ Log viewer only | ✅ CloudWatch | ✅ Application Insights |
| Read replicas | ❌ | ✅ Multi-AZ | ✅ |
| Compliance (IRAP/AuSSO) | ❌ | ✅ | ✅ |
| Sydney region | ❌ Singapore only | ✅ | ✅ |

### Daily.co Region Alignment

A key concern with Railway (Singapore) is that Daily's PSTN gateway for +61 Australian numbers is in Sydney. However, Daily supports `ap-southeast-1` (Singapore) as a media server (SFU) region.

With `DAILY_GEO=ap-southeast-1`:
- Voice engine (Railway Singapore) ↔ Daily SFU (Singapore): near-zero latency — same region
- Daily SFU (Singapore) → Daily PSTN gateway (Sydney): Daily's internal private network, not public internet

The remaining Sydney↔Singapore hop is internal to Daily's infrastructure and significantly lower latency than routing the voice engine itself to Singapore over the public internet. This makes Railway Singapore a viable deployment target for Australian voice calls.

## Decision

**Deploy to Railway (Singapore) for MVP. Migrate to AWS `ap-southeast-2` if either condition is met:**
1. Measured P50 voice round-trip latency exceeds 600ms in production.
2. Enterprise compliance (IRAP, AuSSO, or ISM) is required by a client.

This gives a fast path to a working production environment (hours, not weeks) while preserving a clear, well-understood migration path. The Hexagonal Architecture (ADR-001) and Docker containerisation mean the migration changes deployment config only — no application code changes required.

## Consequences

**Positive:**
- Infrastructure is running within hours of starting Phase 3, not weeks.
- Railway's automatic HTTPS, GitHub integration, and encrypted env vars remove significant operational work for MVP.
- Daily Singapore SFU (`ap-southeast-1`) co-locates with Railway Singapore — media latency is minimised.
- Docker images are portable: the same Dockerfile runs on Railway, AWS ECS, or locally.
- Monthly cost is ~$20–60 vs ~$200–500 on AWS — appropriate for pre-revenue validation.

**Negative:**
- No Railway Sydney region — PSTN routing from Daily Singapore SFU to Daily Sydney PSTN gateway adds latency (exact figure to be measured in Phase 3 smoke tests).
- Railway PostgreSQL has no read replicas and less backup configurability than RDS.
- Railway is not IRAP/AuSSO certified — not suitable for government or highly regulated clients.
- Railway's monitoring is minimal — Datadog or Sentry required for production-grade observability.

## Migration Trigger Criteria

Move to AWS `ap-southeast-2` when any of the following occur:

| Trigger | Action |
|---|---|
| P50 voice round-trip > 600ms in smoke tests | Migrate voice engine + DB to AWS Sydney |
| Enterprise/government client contract | Migrate entire stack to AWS (IRAP certified) |
| Read replica required (DB read P99 degrading) | Migrate DB to RDS Multi-AZ; keep Railway for compute |
| Railway reliability SLA insufficient | Migrate to AWS ECS + RDS |

## Configuration

The deployment target is controlled entirely by environment variables and the CI/CD workflow — no application code changes:

```env
# Set to ap-southeast-1 for Railway Singapore, ap-southeast-2 for AWS Sydney
DAILY_GEO=ap-southeast-1
```

See `docs/guides/deployed-setup.md` for step-by-step Railway deployment instructions.
See `docs/guides/local-setup.md` for local development setup.
