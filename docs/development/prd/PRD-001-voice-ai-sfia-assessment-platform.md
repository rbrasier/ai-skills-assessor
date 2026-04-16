# PRD-001: Voice-AI SFIA Skills Assessment Platform

## Status
Draft

## Date
2026-04-16

## Document Owner
AI Skills Assessor Team

## References
- ADR-001: Hexagonal Architecture (Ports & Adapters)
- ADR-003: Monorepo Structure with pnpm Workspaces + Turborepo
- ADR-004: Voice Engine Technology Decisions
- ADR-005: RAG & Vector Store Strategy

---

## 1. Executive Summary

The Voice-AI SFIA Skills Assessment Platform is an automated, voice-driven system that conducts real-time skills assessments against the SFIA 9 (Skills Framework for the Information Age) framework. A candidate receives a phone call from an AI-powered assessment bot that conducts a structured interview, dynamically retrieves relevant SFIA skill definitions via RAG (Retrieval-Augmented Generation), extracts verifiable work claims from the transcript, maps those claims to specific SFIA skill codes and responsibility levels (1–7), and produces a structured report for Subject Matter Expert (SME) review.

The platform targets the Australian market initially, with telephony optimised for +61 numbers and Daily WebRTC infrastructure deployed in the `ap-southeast-2` (Sydney) region.

## 2. Problem Statement

### Current State
Skills assessment against frameworks like SFIA is a manual, time-consuming process:
- Assessors must be trained SFIA practitioners (expensive, scarce).
- Interviews are inconsistent — quality varies by assessor experience.
- No structured claim extraction — assessors rely on memory and notes.
- Turnaround time from interview to report can be days or weeks.
- Scaling beyond a handful of candidates per day is impractical.

### Desired State
An AI-powered system that:
- Conducts consistent, framework-grounded interviews at any scale.
- Dynamically adapts questions based on the candidate's stated skills and evidence.
- Extracts verifiable claims from the conversation in real time.
- Maps claims to SFIA skill codes and levels with LLM-powered analysis.
- Produces a structured report for SME review within minutes of call completion.
- Supports future extension to frameworks beyond SFIA (e.g., TOGAF, ITIL).

## 3. Target Users

| User Type | Description | Primary Need |
|-----------|-------------|-------------|
| **Candidate** | IT professional being assessed | Natural, non-intimidating phone conversation |
| **SME Reviewer** | SFIA practitioner validating AI-extracted claims | Structured report with clear evidence links |
| **Administrator** | HR/L&D staff triggering assessments | Simple trigger mechanism (phone number + candidate ID) |
| **Platform Operator** | Technical team managing the system | Observability, audit trails, deployment controls |

## 4. Core User Journeys

### 4.1 Assessment Trigger (Administrator)
1. Administrator enters candidate phone number (+61 format) and candidate ID into the web portal.
2. System validates the input and enqueues the call.
3. The voice engine initiates an outbound call via Daily transport.
4. Administrator sees call status in real time (dialling, in-progress, completed).

### 4.2 Voice Assessment (Candidate)
1. Candidate receives a phone call.
2. Bot introduces itself, explains the purpose, and gains verbal consent.
3. **Skill Discovery Phase**: Bot asks open-ended questions to identify which SFIA skills the candidate possesses.
4. **Evidence Gathering Phase**: For each identified skill, bot uses RAG-retrieved SFIA definitions to ask targeted probing questions across Levels 1–7.
5. **Interjection Rule**: If candidate speaks for >60 seconds without providing a verifiable work claim, bot interjects once per call with a polite redirect.
6. Bot summarises key points and closes the call.
7. Full transcript and recording are persisted.

### 4.3 Claim Extraction (Automated)
1. Post-call pipeline receives the complete transcript.
2. LLM (Claude 3.5 Sonnet) analyses the transcript to extract discrete claims.
3. Each claim is mapped to a SFIA skill code and responsibility level.
4. A confidence score is assigned to each mapping.
5. Structured report is generated and stored.
6. A unique review link (NanoID-based) is generated for SME access.

### 4.4 SME Review (SME Reviewer)
1. SME receives a unique, secure link.
2. Link opens a review portal showing:
   - Candidate profile summary
   - Extracted claims with verbatim transcript excerpts
   - AI-suggested SFIA skill code and level for each claim
   - Confidence indicators
3. SME can approve, adjust, or reject each claim.
4. SME submits final assessment.
5. Final report is generated and stored.

## 5. System Architecture Overview

### 5.1 Monorepo Structure

```
ai-skills-assessor/
├── apps/
│   ├── web/                          ← Next.js frontend (Tailwind, Lucide-React)
│   │   ├── app/                      ← App Router
│   │   │   ├── (dashboard)/          ← Admin dashboard routes
│   │   │   ├── (review)/             ← SME review routes
│   │   │   └── api/                  ← Next.js API routes
│   │   ├── components/
│   │   └── lib/
│   │
│   └── voice-engine/                 ← Python service (Pipecat + FastAPI)
│       ├── src/
│       │   ├── domain/               ← Core business logic (no infra deps)
│       │   │   ├── ports/            ← Python ABCs / Protocols
│       │   │   ├── models/           ← Domain models
│       │   │   └── services/         ← Assessment orchestration
│       │   ├── adapters/             ← Infrastructure implementations
│       │   │   ├── daily_transport.py
│       │   │   ├── pgvector_knowledge_base.py
│       │   │   └── postgres_persistence.py
│       │   ├── flows/                ← Pipecat Flows state machine
│       │   └── api/                  ← FastAPI routes
│       ├── pyproject.toml
│       └── Dockerfile
│
├── packages/
│   ├── database/                     ← Prisma/Drizzle schema for PostgreSQL
│   │   ├── schema/
│   │   ├── migrations/
│   │   └── seed/
│   │
│   └── shared-types/                 ← Shared JSON schemas
│       ├── src/
│       │   ├── assessment-report.ts  ← TypeScript types
│       │   └── assessment-report.json← JSON Schema (language-agnostic)
│       └── package.json
│
├── docs/
│   └── development/
│       ├── adr/
│       ├── prd/
│       ├── to-be-implemented/
│       ├── implemented/
│       └── contracts/
│
├── pnpm-workspace.yaml
├── turbo.json
└── package.json
```

### 5.2 Hexagonal Architecture Mapping

```
┌─────────────────────────────────────────────────────────────┐
│                        DOMAIN CORE                          │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Assessment Orchestrator                  │  │
│  │   SFIAFlowController  │  ClaimExtractor              │  │
│  │   SkillMatcher         │  ReportGenerator            │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │                    PORTS                              │  │
│  │  AssessmentTrigger (IN)   VoiceTransport (OUT)       │  │
│  │  TranscriptReceiver (IN)  KnowledgeBase (OUT)        │  │
│  │                           Persistence (OUT)           │  │
│  │                           LLMProvider (OUT)           │  │
│  │                           NotificationSender (OUT)    │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          ▲ implements
┌─────────────────────────┴───────────────────────────────────┐
│                      ADAPTERS                                │
│  DailyTransport        │  PgVectorKnowledgeBase             │
│  PostgresPersistence    │  AnthropicLLMProvider              │
│  EmailNotification      │  WebhookNotification              │
└─────────────────────────────────────────────────────────────┘
                          ▲ wires together
┌─────────────────────────┴───────────────────────────────────┐
│                    COMPOSITION ROOT                           │
│  apps/voice-engine/main.py   │   apps/web/api/routes        │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 Port Definitions

| Port | Direction | Interface | Purpose |
|------|-----------|-----------|---------|
| `AssessmentTrigger` | Inbound | `trigger(phone_number: str, candidate_id: str) -> AssessmentSession` | Receives a request to start an assessment call |
| `TranscriptReceiver` | Inbound | `on_transcript_ready(session_id: str, transcript: Transcript) -> None` | Receives completed transcript for post-processing |
| `VoiceTransport` | Outbound | `dial(phone_number: str, config: CallConfig) -> CallConnection` | Initiates and manages the phone call |
| `KnowledgeBase` | Outbound | `query(text: str, framework_type: str, top_k: int) -> list[SkillDefinition]` | Queries vector store for relevant skill definitions |
| `Persistence` | Outbound | `save_transcript(...)`, `save_claims(...)`, `save_report(...)` | Persists all assessment data to PostgreSQL |
| `LLMProvider` | Outbound | `extract_claims(transcript: str) -> list[Claim]` | Calls the LLM for claim extraction and mapping |
| `NotificationSender` | Outbound | `send_review_link(sme_email: str, review_url: str) -> None` | Notifies SME of available review |

## 6. Key Technical Decisions

### 6.1 Voice Engine: Pipecat + Daily
- **Pipecat** provides the real-time voice AI pipeline framework (STT → LLM → TTS).
- **Daily** provides WebRTC transport with PSTN dial-out capability for Australian numbers.
- The `DailyTransport` adapter is configured for `ap-southeast-2` (Sydney) to minimise latency.
- Call recording and transcript logging enabled by default for audit.

### 6.2 RAG: pgvector with Framework-Type Metadata
- SFIA 9 skill definitions are chunked and embedded into pgvector.
- Each vector entry includes a `framework_type` metadata tag (e.g., `"sfia-9"`, `"togaf"`, `"itil"`).
- This makes the knowledge base pluggable for future framework additions.
- The `SkillRetriever` class filters by `framework_type` at query time.

### 6.3 Claim Extraction: Claude 3.5 Sonnet
- Post-call processing uses Anthropic's Claude 3.5 Sonnet for claim extraction.
- Structured output with JSON mode ensures consistent claim format.
- Each claim includes: verbatim quote, interpreted claim, SFIA skill code, level, confidence.

### 6.4 SME Review Links: NanoID
- Each review session gets a NanoID-based URL (e.g., `/review/V1StGXR8_Z5jdHi6B-myT`).
- NanoID provides URL-safe, collision-resistant, non-sequential identifiers.
- Links expire after a configurable TTL (default: 30 days).

## 7. Non-Functional Requirements

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| **Call Latency** | < 500ms round-trip (Sydney region) | Natural conversation feel |
| **Transcript Processing** | < 5 minutes post-call | Fast turnaround for SME review |
| **Concurrent Calls** | 10+ simultaneous | Enterprise pilot scale |
| **Availability** | 99.5% uptime during business hours (AEST) | Reliability for scheduled assessments |
| **Data Residency** | Australian region preferred | Compliance with data sovereignty expectations |
| **Audit Trail** | Full call recordings + transcripts retained for 12 months | Regulatory and quality assurance |
| **Security** | TLS everywhere, review links with NanoID, no PII in URLs | Data protection |

## 8. Data Model (High-Level)

### Core Entities

- **Candidate**: `id`, `name`, `email`, `phone`, `organisation_id`, `created_at`
- **AssessmentSession**: `id`, `candidate_id`, `status`, `triggered_by`, `started_at`, `ended_at`, `recording_url`, `transcript_url`
- **Transcript**: `id`, `session_id`, `full_text`, `segments[]` (speaker, text, timestamp)
- **Claim**: `id`, `session_id`, `verbatim_quote`, `interpreted_claim`, `sfia_skill_code`, `sfia_level`, `confidence`, `sme_status` (pending/approved/adjusted/rejected)
- **AssessmentReport**: `id`, `session_id`, `review_token` (NanoID), `generated_at`, `sme_reviewed_at`, `status`
- **SFIASkill**: `id`, `code`, `name`, `category`, `subcategory`, `description`, `framework_type`, `embedding` (vector)
- **SFIALevel**: `skill_id`, `level` (1–7), `description`, `autonomy`, `influence`, `complexity`, `knowledge`

## 9. Integration Points

| System | Integration | Protocol |
|--------|-------------|----------|
| **Daily.co** | Telephony/WebRTC transport | REST API + WebRTC |
| **Anthropic Claude** | Claim extraction LLM | REST API |
| **PostgreSQL + pgvector** | Persistence + vector store | TCP (pg protocol) |
| **STT Provider** (via Pipecat) | Speech-to-text | WebSocket |
| **TTS Provider** (via Pipecat) | Text-to-speech | WebSocket |

## 10. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Assessment completion rate | > 85% of initiated calls | Calls reaching EvidenceGathering / total calls |
| Claim extraction accuracy | > 80% agreement with SME review | Claims approved without adjustment / total claims |
| SME review time reduction | 50% vs. manual process | Average time from call end to SME sign-off |
| Candidate satisfaction | > 4.0 / 5.0 | Post-call survey score |

## 11. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| PSTN dial-out reliability in AU | High | Medium | Daily has AU presence; fallback to WebRTC browser link |
| LLM hallucination in claim mapping | High | Medium | SME review is mandatory; confidence thresholds flag uncertain claims |
| Latency in voice pipeline | High | Low | Sydney region deployment; Pipecat's streaming architecture |
| SFIA framework version changes | Medium | Low | Versioned framework_type metadata; re-embedding pipeline |
| Candidate refuses AI interview | Medium | Medium | Clear introduction + opt-out mechanism; human assessor fallback |

## 12. Phased Delivery Plan

| Phase | Name | Scope |
|-------|------|-------|
| **Phase 1** | Foundation & Monorepo Scaffold | Project structure, CI/CD, database schema, shared types |
| **Phase 2** | Voice Engine Core | Pipecat service, Daily transport, state machine, interjection logic |
| **Phase 3** | RAG Knowledge Base | pgvector setup, SFIA data ingestion, SkillRetriever, dynamic prompt injection |
| **Phase 4** | Claim Extraction Pipeline | Post-call processing, LLM integration, claim mapping, report generation |
| **Phase 5** | SME Review Portal | Next.js frontend, review UI, claim approval workflow |
| **Phase 6** | Integration & Deployment | End-to-end wiring, Sydney region deployment, latency optimisation, audit logging |

## 13. Out of Scope (v1)

- Multi-framework support (TOGAF, ITIL) — architecture supports it, not delivered in v1.
- Inbound calls (candidate-initiated).
- Mobile app.
- Real-time claim extraction during the call (post-call only in v1).
- Multi-language support (English only in v1).
- SSO / enterprise identity integration.

## 14. Open Questions

1. **STT/TTS provider selection**: Deepgram, Google Cloud Speech, or Azure? Need latency benchmarks for AU region.
2. **Daily pricing model**: Per-minute costs for PSTN dial-out to AU numbers — need commercial review.
3. **SFIA licensing**: Are SFIA 9 skill definitions freely redistributable, or do we need a license from the SFIA Foundation?
4. **Data retention policy**: What is the regulatory requirement for call recordings in AU?
5. **SME notification channel**: Email only, or also Slack/Teams webhook?
