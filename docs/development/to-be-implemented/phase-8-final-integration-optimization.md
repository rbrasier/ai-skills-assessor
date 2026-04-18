# Phase 8: Final Integration & Latency Optimisation

## Status
To Be Implemented

## Date
2026-04-18

## References
- PRD-001: Voice-AI Skills Assessment Platform
- ADR-004: Voice Engine Technology Decisions
- ADR-005: RAG & Vector Store Strategy
- Phases 1–7 (all prerequisites)

## Objective

Conduct end-to-end integration testing across all components (voice engine → assessment workflow → RAG → claim extraction → SME review), optimise latency to meet sub-500ms round-trip targets, implement comprehensive audit logging and observability, and prepare for production scale testing. The infrastructure is already deployed and stable from Phase 3; this phase focuses on integration validation and performance tuning.

---

## 1. Deliverables

### 1.1 End-to-End Integration

**The full flow, wired together:**

```
Admin Dashboard                Voice Engine                     Post-Call Pipeline
     │                              │                                  │
     │  POST /api/assessment/       │                                  │
     │  trigger                     │                                  │
     ├─────────────────────────────▶│                                  │
     │                              │  Create Daily room               │
     │                              │  (ap-southeast-2, recording ON)  │
     │                              │──────▶ Daily API                 │
     │                              │◀────── Room URL + Token          │
     │                              │                                  │
     │                              │  Dial +61 number                 │
     │                              │──────▶ Daily PSTN                │
     │                              │                                  │
     │  { session_id, status }      │  Pipecat Pipeline Running        │
     │◀─────────────────────────────│  STT → LLM → TTS                │
     │                              │  (RAG context injected)          │
     │                              │                                  │
     │  Poll status                 │  Call ends                       │
     │──────────────────────────────│─────────────────────────────────▶│
     │                              │  Save transcript                 │
     │                              │                                  │
     │                              │                                  │  Extract claims (Claude)
     │                              │                                  │  Map to SFIA skills
     │                              │                                  │  Generate report
     │                              │                                  │  Create NanoID link
     │                              │                                  │
     │                              │  POST /process complete          │
     │                              │◀─────────────────────────────────│
     │                              │                                  │
SME Review                         │                                  │
     │  GET /review/{token}         │                                  │
     │─────────────────────────────▶│                                  │
     │  { report, claims }          │                                  │
     │◀─────────────────────────────│                                  │
     │                              │                                  │
     │  PATCH /review/{token}/      │                                  │
     │  claims/{id}                 │                                  │
     │─────────────────────────────▶│  Persist SME decisions           │
     │                              │                                  │
     │  POST /review/{token}/submit │                                  │
     │─────────────────────────────▶│  Finalise report                 │
```

### 1.2 Composition Root

**File:** `apps/voice-engine/src/main.py`

This is where all adapters are wired together (Hexagonal Architecture composition root).

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncpg

from config import Settings
from adapters.daily_transport import DailyVoiceTransport
from adapters.pgvector_knowledge_base import PgVectorKnowledgeBase
from adapters.postgres_persistence import PostgresPersistence
from adapters.anthropic_llm_provider import AnthropicLLMProvider
from adapters.openai_embedder import OpenAIEmbeddingService
from domain.services.assessment_orchestrator import AssessmentOrchestrator
from domain.services.claim_extractor import ClaimExtractor
from domain.services.report_generator import ReportGenerator
from domain.services.post_call_pipeline import PostCallPipeline
from api.routes import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    
    # Database pool
    db_pool = await asyncpg.create_pool(settings.database_url, min_size=5, max_size=20)
    
    # Adapters
    embedder = OpenAIEmbeddingService(api_key=settings.openai_api_key)
    voice_transport = DailyVoiceTransport(api_key=settings.daily_api_key)
    knowledge_base = PgVectorKnowledgeBase(db_pool=db_pool, embedder=embedder)
    persistence = PostgresPersistence(db_pool=db_pool)
    llm_provider = AnthropicLLMProvider(api_key=settings.anthropic_api_key)
    
    # Domain services
    orchestrator = AssessmentOrchestrator(
        voice_transport=voice_transport,
        knowledge_base=knowledge_base,
        persistence=persistence,
        config=settings,
    )
    claim_extractor = ClaimExtractor(
        llm_provider=llm_provider,
        knowledge_base=knowledge_base,
        persistence=persistence,
    )
    report_generator = ReportGenerator(
        persistence=persistence,
        base_url=settings.app_base_url,
    )
    post_call_pipeline = PostCallPipeline(
        claim_extractor=claim_extractor,
        report_generator=report_generator,
        persistence=persistence,
    )
    
    # Make services available to routes
    app.state.orchestrator = orchestrator
    app.state.persistence = persistence
    app.state.post_call_pipeline = post_call_pipeline
    
    yield
    
    await db_pool.close()

app = FastAPI(
    title="Voice-AI SFIA Skills Assessment Engine",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
```

### 1.3 Daily Transport Configuration (Sydney Region)

**Room creation parameters:**

```python
DAILY_ROOM_CONFIG = {
    "properties": {
        "enable_recording": "cloud",
        "enable_transcription": True,
        "geo": "ap-southeast-2",
        "exp": int(time.time()) + 3600,
        "max_participants": 2,
        "enable_chat": False,
        "enable_screenshare": False,
        "sip": {
            "display_name": "SFIA Assessment",
            "video": False,
            "sip_mode": "dial-out",
            "num_endpoints": 1,
        },
    }
}
```

**Region verification:**
- Validate that the Daily room is created in Sydney by checking the room's `geo` property in the API response.
- Log a warning if the room is assigned to a different region (fallback scenario).

### 1.4 Call Recording & Transcript Audit

**Recording retrieval (post-call):**

```python
async def retrieve_recording(room_name: str) -> str | None:
    """Retrieve the recording URL from Daily after call ends."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.daily.co/v1/recordings?room_name={room_name}",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        recordings = response.json()["data"]
        if recordings:
            return recordings[0]["download_link"]
    return None
```

**Audit trail persisted per session:**

| Field | Source | Storage |
|-------|--------|---------|
| Full transcript (text) | Pipecat context aggregator | `transcripts` table |
| Call recording (audio) | Daily cloud recording | URL in `assessment_sessions.recording_url` |
| Transcript segments (timestamped) | Daily transcription + Pipecat | `transcript_segments` table |
| Extracted claims | Claude LLM | `claims` table |
| SME review decisions | Review portal | `claims` table (sme_status, sme_notes) |
| Final report | Report generator | `assessment_reports` table |

### 1.5 Latency Optimisation

**Target:** < 500ms round-trip for voice interaction (user speech → bot response start)

**Optimisation strategies:**

| Component | Strategy | Expected Impact |
|-----------|----------|-----------------|
| **Daily Transport** | Sydney region (`ap-southeast-2`) | -100-200ms vs US region |
| **STT** | Use Deepgram (streaming mode) | ~200ms first-word latency |
| **LLM** | Use streaming responses; start TTS as tokens arrive | -500-1000ms vs waiting for full response |
| **TTS** | Use streaming TTS (ElevenLabs Turbo v2) | ~200ms first-byte latency |
| **RAG** | pgvector query < 10ms; cache frequent queries | Negligible overhead |
| **Pipeline** | Pipecat's frame-based streaming eliminates batch boundaries | Continuous flow |
| **VAD** | Silero VAD for fast end-of-speech detection | -200-500ms vs fixed silence timeout |

**Latency measurement:**

```python
import time

class LatencyTracker:
    def __init__(self):
        self.user_speech_end: float = 0
        self.bot_speech_start: float = 0
    
    def on_user_stopped_speaking(self):
        self.user_speech_end = time.monotonic()
    
    def on_bot_started_speaking(self):
        self.bot_speech_start = time.monotonic()
        latency_ms = (self.bot_speech_start - self.user_speech_end) * 1000
        logger.info(f"Response latency: {latency_ms:.0f}ms")
        metrics.record_latency(latency_ms)
```

### 1.6 Observability & Monitoring

**Structured logging:**

```python
import structlog

logger = structlog.get_logger()

logger.info(
    "assessment.call_started",
    session_id=session.id,
    candidate_id=session.candidate_id,
    region="ap-southeast-2",
)

logger.info(
    "assessment.claim_extracted",
    session_id=session.id,
    claim_count=len(claims),
    avg_confidence=avg_confidence,
)
```

**Key metrics to track:**

| Metric | Type | Alert Threshold |
|--------|------|-----------------|
| `assessment.response_latency_ms` | Histogram | p95 > 1000ms |
| `assessment.call_duration_seconds` | Histogram | > 3600s (1 hour) |
| `assessment.call_completion_rate` | Counter ratio | < 0.80 |
| `assessment.claims_per_session` | Histogram | 0 (no claims extracted) |
| `assessment.rag_query_latency_ms` | Histogram | p95 > 500ms |
| `assessment.llm_extraction_latency_s` | Histogram | > 120s |
| `daily.room_creation_errors` | Counter | Any |
| `daily.pstn_dial_failures` | Counter | > 3 consecutive |

### 1.7 Production Readiness Checklist

**Note**: Infrastructure deployment is completed in Phase 3. This phase validates and optimizes the deployed system.

**Pre-production checklist:**
- [ ] All services are deployed and healthy (Phase 3).
- [ ] Database is backed up and replication is tested.
- [ ] Monitoring dashboards are configured and populated with real data.
- [ ] Alerts are firing correctly (e.g., latency > 1s, call failures > 5%).
- [ ] Log aggregation is working (Cloudwatch / Application Insights).
- [ ] Load testing has completed (10 concurrent calls).
- [ ] Latency targets verified in production (p50 < 500ms, p95 < 1000ms).
- [ ] All integrations tested end-to-end.
- [ ] SME review portal is accessible and functional.
- [ ] Audit logs are complete (call recordings, transcripts, claim mappings).
- [ ] Disaster recovery plan is tested.
- [ ] On-call runbook is documented.

### 1.8 Environment Variables

```env
# Database
DATABASE_URL=postgresql://user:pass@host:5432/sfia_assessor

# Daily
DAILY_API_KEY=xxx
DAILY_API_URL=https://api.daily.co/v1

# LLM / AI
OPENAI_API_KEY=xxx
ANTHROPIC_API_KEY=xxx
DEEPGRAM_API_KEY=xxx
ELEVENLABS_API_KEY=xxx
ELEVENLABS_VOICE_ID=xxx

# Application
APP_BASE_URL=https://sfia-assessor.example.com
VOICE_ENGINE_URL=http://voice-engine:8000

# Feature Flags
ENABLE_CALL_RECORDING=true
ENABLE_INTERJECTION=true
INTERJECTION_TIMEOUT_SECONDS=60
REVIEW_LINK_EXPIRY_DAYS=30
```

---

## 2. Integration Test Plan

### End-to-End Scenarios

| Scenario | Steps | Expected Result |
|----------|-------|-----------------|
| **Happy path** | Trigger → Call → Discover → Evidence → Close → Process → Review | Report with claims, reviewable via link |
| **Candidate declines** | Trigger → Call → Introduction (decline) → Close | Session status: "completed", no claims |
| **Call fails (no answer)** | Trigger → Dial → Timeout | Session status: "failed", error logged |
| **Long monologue (interjection)** | Candidate talks >60s without claim | Bot interjects once, then continues |
| **Empty transcript** | Call connects but minimal speech | Report generated with 0 claims |
| **SME adjusts claims** | Review → Adjust levels → Submit | Report reflects adjusted levels |
| **Expired review link** | Access link after 30 days | 404 response |

### Load Testing

- **Target**: 10 concurrent calls
- **Tool**: Locust or k6 for API endpoint testing
- **Metrics**: Response latency, error rate, database connection pool utilisation

---

## 3. Acceptance Criteria

- [ ] Full end-to-end flow works: trigger → call → process → review → submit.
- [ ] Daily rooms are created in `ap-southeast-2` region.
- [ ] Call recording URLs are captured and persisted.
- [ ] Transcript is persisted with timestamped segments.
- [ ] Voice response latency is < 500ms p50, < 1000ms p95 (measured in Sydney).
- [ ] Post-call processing completes within 5 minutes.
- [ ] Structured logging is in place for all key events.
- [ ] Metrics are exported for latency, call completion, and error rates.
- [ ] Environment variables are documented and validated at startup.
- [ ] Docker Compose file exists for local development.
- [ ] CI pipeline runs all tests (Python + TypeScript).
- [ ] 10 concurrent calls can be handled without degradation.

## 4. Dependencies

- **All prior phases** (1–7) must be complete.
- **Phase 3 Infrastructure**: Production AWS/Azure environment already deployed and stable.
- **External services**: Daily account with PSTN enabled, Anthropic API access, OpenAI API access, Deepgram API access, ElevenLabs API access.
- **Infrastructure**: PostgreSQL with pgvector in AU region (deployed in Phase 3), compute in AU region (deployed in Phase 3).

## 5. Risks

| Risk | Mitigation |
|------|------------|
| Daily PSTN costs higher than expected | Start with WebRTC browser calls for testing; PSTN for production |
| LLM API rate limits during peak | Implement queuing for post-call processing; batch where possible |
| Database connection exhaustion under load | Connection pooling (PgBouncer or asyncpg pool); monitor pool stats |
| Latency regression as features are added | Automated latency benchmarks in CI; alerting on p95 degradation |
| Regional compliance (data residency) | Ensure all data stays in AU region; audit data flows |
