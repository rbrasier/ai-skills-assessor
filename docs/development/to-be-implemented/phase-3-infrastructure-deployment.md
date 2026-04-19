# Phase 3: Infrastructure Deployment (Sydney Region)

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

Deploy the basic voice engine and supporting infrastructure to AWS or Azure in the `ap-southeast-2` (Sydney) region. Validate that CI/CD pipeline works, database connectivity is stable, Daily PSTN dial-out functions in production, and basic call tracking works end-to-end in a live environment before building additional feature complexity.

By the end of Phase 3, the platform is running in a production-like environment with the basic voice engine working and tracked calls visible in the production admin dashboard.

---

## 1. Deliverables

### 1.1 AWS/Azure Infrastructure Setup

**Scope**: PostgreSQL instance, networking, security groups, load balancing.

**Decisions needed**:
- Cloud provider: AWS or Azure (or hybrid)?
- Database: AWS RDS PostgreSQL (ap-southeast-2) or Azure Database for PostgreSQL?
- Compute: ECS Fargate (AWS) or Container Instances (Azure) for voice-engine service?
- Load balancing: ALB (AWS) or Application Gateway (Azure)?

**Deliverables**:
- PostgreSQL instance in Sydney region with pgvector extension enabled.
- VPC/networking configured for security (public API endpoints, private database).
- Security groups/firewall rules for Daily WebRTC + PSTN traffic.
- Secrets management (Daily API key, database credentials) via AWS Secrets Manager or Azure Key Vault.
- Database migration scripts ready to run on deployment.

### 1.2 CI/CD Pipeline

**File**: `.github/workflows/deploy.yml`

Implements automated deployment on `main` branch.

**Steps**:
1. Build Docker images for voice-engine (Python) and web (Next.js).
2. Run unit tests and type checks.
3. Push images to container registry (ECR/ACR).
4. Deploy to staging environment (run full test suite against deployed services).
5. On approval, deploy to production.

**Example GitHub Actions workflow sketch:**

```yaml
name: Deploy to Sydney

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

**File**: `.env.production`

Secrets and configuration for production environment.

```env
# Daily.co
DAILY_API_KEY=<production_key>

# Database
DATABASE_URL=postgresql://user:pass@rds-sydney.amazonaws.com:5432/ai_skills_assessor

# AWS/Azure
AWS_REGION=ap-southeast-2
AWS_ECR_REGISTRY=123456789.dkr.ecr.ap-southeast-2.amazonaws.com

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

**Note**: Actual secrets are stored in AWS Secrets Manager or Azure Key Vault, not in `.env.production`.

### 1.6 Monitoring & Logging

**Scope**: CloudWatch (AWS) or Application Insights (Azure) for centralized logging.

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

- [ ] PostgreSQL instance running in `ap-southeast-2` with pgvector extension.
- [ ] Database schema applied (candidates, sessions, reports, skill_embeddings tables).
- [ ] GitHub Actions CI/CD pipeline created and triggers on push to `main`.
- [ ] Docker images build successfully for both voice-engine and web.
- [ ] Images push to container registry (ECR/ACR).
- [ ] Staging environment available and deployments work.
- [ ] Production environment available with secure access.
- [ ] Secrets management configured (no hardcoded keys).
- [ ] TLS/HTTPS enabled on all endpoints.
- [ ] Basic health check endpoint works: GET `/health` returns 200.
- [ ] Smoke test passes: can trigger a call and check status in production.
- [ ] Monitoring/logging configured and accessible.
- [ ] Database backups automated and tested.
- [ ] Rollback procedure documented and tested.
- [ ] Daily API connectivity verified (can successfully dial in Sydney region).

---

## 3. Key Decisions

### Cloud Provider Selection
- **AWS**: Mature, Sydney region (ap-southeast-2), good pricing, RDS PostgreSQL with pgvector support.
- **Azure**: Also has ap-southeast-2 Sydney region, Azure Database for PostgreSQL.
- **Decision**: TBD — depends on existing corporate cloud agreements.

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
- **External**: AWS/Azure account, Daily.co account, credit card for cloud infrastructure.

---

## 5. Estimated Effort

- **Infrastructure setup**: Medium — networking, security groups, database provisioning.
- **CI/CD pipeline**: Medium — GitHub Actions workflow, testing, staging environment.
- **Containerization**: Low — Dockerfiles already drafted in Phase 1.
- **Monitoring setup**: Low — cloud provider's default dashboards sufficient for MVP.
- **Testing & validation**: Low — smoke tests, manual verification.

---

## 6. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Daily PSTN dial-out fails in production | High | Test with real AU phone numbers early; verify Daily Sydney PoP is operational |
| Database performance degrades under load | Medium | Use read replica; monitor query latency; optimize indexes in Phase 8 |
| Cost overruns (cloud infra, Daily dial-out) | Medium | Set up billing alerts; estimate costs before Phase 3; use spot instances if possible |
| CI/CD pipeline too slow (blocks deployments) | Low | Optimize build cache; parallelize tests; acceptable if < 10 minutes for full pipeline |
| Secrets leaked in logs or environment variables | High | Use cloud provider's secret management; audit logs for accidental exposure |

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

## 8. Notes

- This phase is intentionally **minimal in scope**: get the basic voice engine running in a production environment, nothing more.
- Feature development (assessment workflow, RAG, claim extraction) happens in Phases 4–7 **on the validated infrastructure**.
- Phase 8 handles production optimization (latency tuning, monitoring refinement, stress testing).
- If Phase 3 identifies infrastructure issues, those are fixed immediately before moving to Phase 4.
