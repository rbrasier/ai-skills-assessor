# Phase 3: Infrastructure Deployment

## Status
To Be Implemented

## Date
2026-04-18

## References
- PRD-001: Voice-AI Skills Assessment Platform
- ADR-003: Monorepo Structure (CI/CD pipeline)
- Phase 1: Foundation & Monorepo Scaffold (prerequisite)
- Phase 2: Basic Voice Engine & Call Tracking (prerequisite)

## Objective

Deploy the basic voice engine and supporting infrastructure to a cloud provider in the Asia-Pacific region (Singapore or Sydney). Validate that CI/CD pipeline works, database connectivity is stable, Daily PSTN dial-out functions in production, and basic call tracking works end-to-end in a live environment before building additional feature complexity.

By the end of Phase 3, the platform is running in a production-like environment with the basic voice engine working and tracked calls visible in the production admin dashboard.

---

## 1. Deliverables

### 1.1 Cloud Infrastructure Setup

**Scope**: PostgreSQL instance, networking, secrets management, compute.

**Decisions needed** (see Section 3 for full analysis):
- Cloud provider: Railway (Singapore), AWS (Sydney), or Azure (Sydney)?
- Database: Railway PostgreSQL, AWS RDS, or Azure Database for PostgreSQL?
- Compute: Railway services, ECS Fargate (AWS), or Container Instances (Azure)?

**Deliverables**:
- PostgreSQL instance in Asia-Pacific region with pgvector extension enabled.
- Network security configured (public API endpoints, private database access).
- Firewall/port rules for Daily WebRTC + PSTN traffic (outbound UDP + TCP).
- Secrets management configured (Railway env vars, or AWS Secrets Manager / Azure Key Vault).
- Database migration scripts ready to run on deployment.

**Daily SFU region note**: Daily supports `ap-southeast-1` (Singapore) as a media server region. If deploying to Railway Singapore, configure Daily rooms with `geo: "ap-southeast-1"` so the voice engine and Daily's SFU are co-located — minimising media latency. PSTN dial-out to Australian +61 numbers will route through Daily's internal network to their Sydney PSTN gateway regardless of SFU region.

### 1.2 CI/CD Pipeline

**File**: `.github/workflows/deploy.yml`

Implements automated deployment on `main` branch. The pipeline structure differs slightly by provider — Railway removes the container registry step; AWS/Azure require ECR/ACR.

**Steps (common to all providers)**:
1. Run unit tests and type checks.
2. Build Docker images for voice-engine (Python) and web (Next.js).
3. Deploy to staging environment and run smoke tests.
4. On approval, deploy to production.

**Option A — Railway (simplified):**

```yaml
name: Deploy (Railway)

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pnpm install --frozen-lockfile
      - run: pnpm test
      - run: pnpm lint

  deploy:
    needs: test
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: railway/deploy@v1
        with:
          service: voice-engine
          token: ${{ secrets.RAILWAY_TOKEN }}
      - uses: railway/deploy@v1
        with:
          service: web
          token: ${{ secrets.RAILWAY_TOKEN }}
```

> Railway can also auto-deploy directly from GitHub without GitHub Actions — useful for early-stage development. GitHub Actions adds the test gate before Railway triggers the deploy.

**Option B — AWS/Azure (full pipeline):**

```yaml
name: Deploy (AWS)

on:
  push:
    branches: [main]

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v5
        with:
          context: apps/voice-engine
          tags: ${{ env.ECR_REGISTRY }}/${{ env.ECR_REPO }}:latest
          push: true
      - run: pnpm install --frozen-lockfile
      - run: pnpm test
      - run: pnpm lint

  deploy-staging:
    needs: build-and-test
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to staging
        run: |
          # Deploy voice-engine to staging ECS/ACI
          # Run smoke tests against staging

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    environment: production
    steps:
      - name: Deploy to production
        run: |
          # Deploy voice-engine + web to production
          # Run health checks
```

### 1.3 Database Initialization & Migrations

**File**: `packages/database/migrations/` + deployment scripts

Ensure database is set up with all required tables and extensions.

**Checklist**:
- [ ] PostgreSQL 15+ deployed with pgvector extension.
- [ ] `assessment_sessions` table created.
- [ ] `candidates` table created.
- [ ] `assessment_reports` table created.
- [ ] `skill_embeddings` table created (for future RAG use).
- [ ] Indexes created.
- [ ] Migration rollback scripts tested.
- [ ] Database backups configured (daily, retained 30 days).

### 1.4 Containerization

**Files**:
- `apps/voice-engine/Dockerfile`
- `apps/web/Dockerfile`
- `docker-compose.yml` (for local testing of multi-container setup)

**voice-engine Dockerfile:**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml pyproject.lock* ./
RUN pip install -e .

COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**web Dockerfile:**

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY . .
RUN pnpm install --frozen-lockfile
RUN pnpm --filter @ai-skills-assessor/web run build

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/apps/web/.next ./.next
COPY --from=builder /app/apps/web/public ./public
COPY --from=builder /app/apps/web/package.json ./
RUN pnpm install --prod

EXPOSE 3000
CMD ["pnpm", "start"]
```

### 1.5 Environment Configuration

Secrets and configuration for production environment. The variables are the same regardless of provider; only the storage mechanism differs.

```env
# Daily.co
DAILY_API_KEY=<production_key>
DAILY_GEO=ap-southeast-1          # Singapore SFU (Railway) or ap-southeast-2 (AWS Sydney)

# Database
DATABASE_URL=postgresql://user:pass@<host>:5432/ai_skills_assessor

# STT/TTS (to be determined in Phase 2)
STT_PROVIDER=deepgram
STT_API_KEY=<production_key>
TTS_PROVIDER=elevenlabs
TTS_API_KEY=<production_key>

# Application URLs
VOICE_ENGINE_URL=https://api.assessor.example.com
CANDIDATE_PORTAL_URL=https://assessor.example.com
ADMIN_DASHBOARD_URL=https://admin.assessor.example.com
```

**Secret storage by provider**:
- **Railway**: Environment variables set per-service in Railway dashboard (encrypted at rest, not in `.env` files)
- **AWS**: AWS Secrets Manager (`ap-southeast-2`), injected at container startup via ECS task definition
- **Azure**: Azure Key Vault, injected via managed identity

### 1.6 Monitoring & Logging

**Scope**: Railway built-in log viewer, or CloudWatch (AWS) / Application Insights (Azure) for centralized logging. For Railway, a third-party tool (Datadog, Grafana Cloud, or Sentry) is needed for metric dashboards beyond basic log streaming.

**Metrics to track**:
- Call success rate (calls completed / calls initiated)
- Call setup latency (dial → connected time)
- Database query latency (P50, P95, P99)
- Voice engine uptime (% of time service is healthy)
- Daily API errors (rate limit hits, PSTN failures)

**Logs**:
- Voice engine logs (call lifecycle events, errors)
- Database connection logs
- CI/CD deployment logs (for audit trail)

### 1.7 Smoke Tests

**File**: `apps/voice-engine/tests/smoke_test.py`

Basic end-to-end test that verifies production is healthy.

```python
async def test_smoke_production():
    """Smoke test: candidate intake → call trigger → status polling works end-to-end."""
    client = AsyncClient(base_url="https://api.assessor.example.com")
    
    # 1. Create/lookup candidate (Step 01 of intake form)
    response = await client.post(
        "/api/v1/assessment/candidate",
        json={
            "work_email": "smoke-test@example.com",
            "first_name": "Smoke",
            "last_name": "Test",
            "employee_id": "SMOKE-001",
        },
    )
    assert response.status_code == 200
    candidate_id = response.json()["candidate_id"]

    # 2. Trigger call (Step 02 — accepts international numbers)
    response = await client.post(
        "/api/v1/assessment/trigger",
        json={
            "candidate_id": candidate_id,
            "phone_number": "+61400000000",  # Test number
        },
    )
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    
    # 3. Check status endpoint works
    response = await client.get(f"/api/v1/assessment/{session_id}/status")
    assert response.status_code == 200
    
    # 4. Check admin sessions endpoint works (read-only monitoring)
    response = await client.get("/api/v1/admin/sessions?limit=1")
    assert response.status_code == 200

    # 5. Verify database is reachable
    response = await client.get("/health")
    assert response.status_code == 200
```

---

## 2. Acceptance Criteria

- [ ] PostgreSQL instance running in Asia-Pacific region (Singapore or Sydney) with pgvector extension.
- [ ] Database schema applied (candidates, sessions, reports, skill_embeddings tables).
- [ ] CI/CD pipeline created and triggers on push to `main` (Railway auto-deploy or GitHub Actions).
- [ ] Docker images build successfully for both voice-engine and web.
- [ ] Staging environment available and deployments work.
- [ ] Production environment available with secure access.
- [ ] Secrets management configured (no hardcoded keys).
- [ ] TLS/HTTPS enabled on all endpoints (automatic on Railway; manual cert on AWS/Azure).
- [ ] Basic health check endpoint works: GET `/health` returns 200.
- [ ] Smoke test passes: can trigger a call and check status in production.
- [ ] Monitoring/logging configured and accessible.
- [ ] Database backups automated and tested.
- [ ] Rollback procedure documented and tested.
- [ ] Daily API connectivity verified (PSTN dial-out to Australian +61 numbers works).
- [ ] Voice call P50 round-trip latency measured and acceptable (&lt; 600ms end-to-end for AI response).

---

## 3. Key Decisions

### Cloud Provider Selection

Three viable options, ordered by setup complexity (lowest to highest):

#### Option 1: Railway (Singapore — `asia-southeast1`) — Recommended for MVP

Railway is a PaaS (similar to Heroku) that deploys Docker containers directly from GitHub. It has a Singapore region and supports PostgreSQL with pgvector.

**Daily.co alignment**: Daily supports `ap-southeast-1` (Singapore) as a media server region. Configuring `DAILY_GEO=ap-southeast-1` co-locates the voice engine and Daily's SFU in Singapore, giving near-zero media latency. PSTN dial-out to Australian +61 numbers routes through Daily's internal network to their Sydney PSTN gateway — this is Daily's private network, not the public internet, so the added hop is significantly lower than the naive Singapore↔Sydney public internet estimate.

| Dimension | Railway |
|---|---|
| Setup time | Hours (no VPC, IAM, or container registry) |
| Monthly cost (MVP) | ~$20–60/month |
| PostgreSQL + pgvector | ✅ Built-in |
| HTTPS/TLS | ✅ Automatic |
| Secrets management | ✅ Per-service env vars (encrypted) |
| CI/CD | ✅ Auto-deploy from GitHub (or GitHub Actions + Railway CLI) |
| Monitoring | ⚠️ Basic log viewer only — add Datadog/Sentry for metrics |
| Read replicas | ❌ Not available |
| Compliance (AuSSO/ISM) | ❌ Not certified |
| Sydney region | ❌ Singapore only |
| Horizontal autoscaling | ⚠️ Manual; limited vs ECS autoscaling |

**Risks**: No read replicas, limited backup control vs RDS, no Sydney region (Daily PSTN to AU adds internal Daily network hop). Recommended for MVP and early validation — migrate to AWS if compliance or latency requirements demand it.

#### Option 2: AWS (Sydney — `ap-southeast-2`)

RDS PostgreSQL with pgvector, ECS Fargate for compute, ALB for load balancing. Native Sydney region means voice engine and Daily PSTN gateway are in the same region.

| Dimension | AWS |
|---|---|
| Setup time | Days–weeks (VPC, IAM roles, ECS, ECR, RDS, ALB, Secrets Manager) |
| Monthly cost (MVP) | ~$200–500/month |
| PostgreSQL + pgvector | ✅ RDS with pgvector extension |
| HTTPS/TLS | ✅ ACM certificates |
| Secrets management | ✅ Secrets Manager |
| CI/CD | GitHub Actions → ECR → ECS deploy |
| Monitoring | ✅ CloudWatch (metrics, logs, alarms) |
| Read replicas | ✅ RDS Multi-AZ |
| Compliance | ✅ IRAP/AuSSO certified |
| Sydney region | ✅ `ap-southeast-2` — same region as Daily PSTN |

**Best for**: production workloads with compliance requirements or where Sydney co-location with Daily PSTN is mandated.

#### Option 3: Azure (Sydney — `australiaeast`)

Equivalent to AWS in capability; use if the organisation has existing Azure agreements.

| Dimension | Azure |
|---|---|
| Setup time | Days–weeks (similar to AWS) |
| Monthly cost (MVP) | ~$200–500/month |
| PostgreSQL + pgvector | ✅ Azure Database for PostgreSQL Flexible Server |
| HTTPS/TLS | ✅ App Gateway / Front Door |
| Secrets management | ✅ Key Vault |
| CI/CD | GitHub Actions → ACR → Container Apps deploy |
| Monitoring | ✅ Application Insights |
| Sydney region | ✅ `australiaeast` |

**Decision**: TBD — Railway recommended for MVP speed. Migrate to AWS `ap-southeast-2` if latency testing shows unacceptable call quality, or if enterprise compliance (IRAP/AuSSO) is required.

### CI/CD Strategy
- GitHub Actions (free, integrated with GitHub, no additional cost for private repo).
- Alternative: GitLab CI, AWS CodePipeline (if using AWS), or Azure Pipelines.
- **Decision**: GitHub Actions (assumed in this doc).

### Database Backups
- Automated daily snapshots, retained for 30 days.
- Separate read replica in another availability zone for disaster recovery.
- **Decision**: Use cloud provider's native backup + replication (RDS automatic backups or Azure backup).

---

## 4. Dependencies

- **Phase 1**: Monorepo, CI/CD skeleton, Dockerfile stubs.
- **Phase 2**: Working voice engine code (to be deployed).
- **External**: Railway account (MVP) or AWS/Azure account (production), Daily.co account, credit card for cloud infrastructure.

---

## 5. Estimated Effort

- **Infrastructure setup**: Low (Railway) / Medium–High (AWS/Azure) — Railway eliminates VPC, IAM, and container registry setup.
- **CI/CD pipeline**: Low (Railway auto-deploy) / Medium (GitHub Actions → ECR → ECS for AWS).
- **Containerization**: Low — Dockerfiles already drafted in Phase 1.
- **Monitoring setup**: Low — Railway log viewer sufficient for MVP; add Datadog/Sentry if metric dashboards are required.
- **Testing & validation**: Low — smoke tests, manual voice call verification, latency measurement.

---

## 6. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Daily PSTN dial-out fails in production | High | Test with real AU phone numbers early; verify `DAILY_GEO` matches deployment region |
| Singapore↔Sydney PSTN latency unacceptable (Railway path) | Medium | Measure P50 voice round-trip in smoke tests; migrate to AWS Sydney if > 600ms total |
| Railway PostgreSQL backup/recovery insufficient | Medium | Test backup restore before go-live; consider AWS RDS if 30-day retention with point-in-time recovery is required |
| Database performance degrades under load | Medium | Monitor query latency; Railway lacks read replicas — migrate to RDS if P99 degrades |
| Cost overruns (cloud infra, Daily dial-out) | Medium | Set billing alerts; Railway is ~$20–60/month for MVP vs ~$200–500/month on AWS |
| CI/CD pipeline too slow (blocks deployments) | Low | Optimize build cache; parallelize tests; acceptable if < 10 minutes for full pipeline |
| Secrets leaked in logs or environment variables | High | Use provider secret management; audit logs for accidental exposure; never commit `.env.production` |
| Railway outage (no multi-AZ) | Low | Accept for MVP; AWS Multi-AZ for production if uptime SLA is required |

---

## 7. Success Criteria

By the end of Phase 3:
- ✅ Candidate portal is live at a public URL (e.g., `https://assessor.example.com`).
- ✅ A candidate can self-initiate an assessment call via the intake form in production.
- ✅ Admin dashboard is live for read-only monitoring (e.g., `https://admin.assessor.example.com`).
- ✅ Call status updates appear in real-time on the candidate portal.
- ✅ Call duration is tracked and displayed.
- ✅ Calls to real phone numbers work in production (international numbers supported).
- ✅ Logs are centralized and searchable.
- ✅ Database is backed up automatically.
- ✅ Team can deploy new code via `git push main` without manual steps.

---

## 8. Definition of Done

Before closing Phase 3, verify all of the following:

- [ ] All acceptance criteria in Section 2 are checked off.
- [ ] `docs/guides/deployed-setup.md` reflects the actual deployed configuration — env var names, service layout, Daily region, and migration steps match what is running in production.
- [ ] `docs/guides/local-setup.md` is accurate against the current codebase — prerequisites, install steps, and smoke test commands all work on a clean checkout.
- [ ] Any discrepancies found between the guides and the implementation are fixed in the guides (not papered over).
- [ ] Phase doc moved from `to-be-implemented/` to `implemented/{version}/` with implementation notes.

---

## 9. Notes

- This phase is intentionally **minimal in scope**: get the basic voice engine running in a production environment, nothing more.
- Feature development (assessment workflow, RAG, claim extraction) happens in Phases 4–7 **on the validated infrastructure**.
- Phase 8 handles production optimization (latency tuning, monitoring refinement, stress testing).
- If Phase 3 identifies infrastructure issues, those are fixed immediately before moving to Phase 4.
