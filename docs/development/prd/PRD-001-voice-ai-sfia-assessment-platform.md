# PRD-001: Voice-AI SFIA Skills Assessment Platform

## Status
Draft

## Date
2026-04-18 (Last Updated)

## Document Owner
AI Skills Assessor Team

## References
- ADR-001: Hexagonal Architecture (Ports & Adapters)
- ADR-003: Monorepo Structure with pnpm Workspaces + Turborepo
- PRD-002: Assessment Interview Workflow (details of how interviews are conducted)

---

## 1. Executive Summary

The Voice-AI Skills Assessment Platform is an automated system that conducts skills assessments via phone call and produces structured reports for Subject Matter Expert (SME) review. 

**High-level workflow:**
1. Administrator triggers an assessment call for a candidate (via web dashboard).
2. An AI bot conducts a structured interview with the candidate (see PRD-002 for interview details).
3. Post-call, the system extracts verifiable work claims and maps them to framework skills.
4. SME receives a structured report and review portal to approve, adjust, or reject claims.
5. Final assessment is signed off and stored.

**Framework Support**: Extensible design supports SFIA 9 initially, with support for TOGAF, ITIL, and other frameworks via metadata tagging (see PRD-002, Data Model section).

**Geographic Focus**: Australian market, with telephony optimised for +61 numbers and infrastructure in `ap-southeast-2` (Sydney region).

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
| **Candidate** | IT professional being assessed | Conversation with AI bot; clear explanation of framework being assessed |
| **SME Reviewer** | Subject matter expert validating AI-extracted claims | Structured report with clear evidence (transcript excerpts), confidence indicators, easy claim approval/adjustment workflow |
| **Administrator** | HR/L&D staff managing assessments | Simple trigger mechanism (phone number + candidate ID), real-time call status, access to completed reports |

## 4. Core User Journeys

### 4.1 Assessment Trigger (Administrator)
1. Administrator enters candidate phone number (+61 format) and candidate ID into the web portal.
2. System validates the input and enqueues the call.
3. The voice engine initiates an outbound call via Daily transport.
4. Administrator sees call status in real time (dialling, in-progress, completed).

### 4.2 Voice Assessment (Candidate)
1. Candidate receives a phone call from the AI bot.
2. Bot introduces itself, explains the assessment, and obtains verbal consent.
3. Bot conducts a structured interview with two phases:
   - **Skill Discovery**: Open-ended questions to understand candidate's background.
   - **Evidence Gathering**: Targeted questions on specific skills with real-world examples.
4. Full call is recorded; transcript is generated via speech-to-text.

_For detailed interview flow, see PRD-002: Assessment Interview Workflow._

### 4.3 Claim Extraction & Report Generation (Automated)
1. Post-call, the system extracts verifiable work claims from the transcript.
2. Each claim is mapped to a framework skill and responsibility level with a confidence score.
3. Claims are grouped into a structured report, ready for SME review.
4. A unique review link (NanoID-based) is generated for secure SME access.

_For detailed extraction pipeline, see PRD-002: Assessment Interview Workflow._

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

### 5.2 Data Flow

```
Admin Dashboard         Voice Engine          Claim Extraction      SME Portal
       │                    │                       │                   │
       ├─ Trigger Call ────>│                       │                   │
       │                    ├─ Interview ──────────>│                   │
       │                    │  (transcript +         │                   │
       │                    │   claims extracted)    │                   │
       │                    │                       ├─ Report Ready ──>│
       │<─ Call Status ─────┤                       │                   │
       │                    │                       │         Approve   │
       │                    │                       │<── Adjust/Reject─┤
       │                    │                       │                   │
       │                    │                       │<─ Final Report ───┤
```

**Voice engine details and architecture are in PRD-002.**

## 6. Key Platform Decisions

### 6.1 SME Review Links: NanoID
- Each assessment report gets a NanoID-based URL (e.g., `/review/V1StGXR8_Z5jdHi6B-myT`).
- NanoID provides URL-safe, collision-resistant, non-sequential identifiers.
- Links expire after 30 days by default (configurable).
- No PII in URLs; links are access-controlled via database.

### 6.2 Framework-Agnostic Architecture
- Assessment system supports any framework (SFIA 9, TOGAF, ITIL, etc.) via metadata tagging.
- Framework type is a property of each assessment session and claim, not a hard-coded choice.
- New frameworks can be added by loading definitions into the knowledge base; no schema migrations.

### 6.3 Voice Interview & Claim Extraction Pipeline
- Interviews are conducted via phone (see PRD-002 for technical details).
- Claims are extracted post-call using LLM analysis of the transcript.
- Each claim includes a confidence score; SME reviews and approves/adjusts/rejects.

**For voice engine architecture and technical decisions (Pipecat, Daily, Claude, pgvector), see PRD-002: Assessment Interview Workflow.**

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

## 8. Data Model (Platform Level)

### Core Entities

| Entity | Purpose | Key Fields |
|--------|---------|-----------|
| **Candidate** | Person being assessed | `id`, `name`, `email`, `phone` (+61 format), `organisation_id`, `created_at` |
| **AssessmentSession** | Single assessment call | `id`, `candidate_id`, `status` (pending/dialling/in-progress/completed/failed), `started_at`, `ended_at`, `framework_type` (e.g., "sfia-9") |
| **AssessmentReport** | Output of assessment + SME review | `id`, `session_id`, `review_token` (NanoID), `status` (generated/in-review/completed), `generated_at`, `sme_reviewed_at` |

**Detailed data structures for interviews, transcripts, claims, and framework definitions are in PRD-002.**

## 9. Platform Integration Points

| System | Integration | Purpose |
|--------|-------------|---------|
| **Email / Notification System** | Send review links to SME | SME invitations, reminders |
| **PostgreSQL** | Persistent data store | Candidates, sessions, reports |
| **Authentication** (TBD) | Access control for SME portal | Secure review link validation |

**Voice engine integrations (Daily, STT/TTS, Claude, pgvector) are detailed in PRD-002.**

## 10. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Report delivery time | < 10 minutes from call end | Time to SME review portal readiness |
| SME review completion rate | > 90% of reports reviewed | Reviews submitted / reports sent |
| Time to SME sign-off | < 1 hour average | Time from report ready to final assessment |
| System uptime | 99.5% during business hours (AEST) | Scheduled assessment reliability |
| SME satisfaction with review UX | > 4.0 / 5.0 | Portal usability and claim clarity |

**Interview-level success metrics (completion rate, claim accuracy, candidate satisfaction) are in PRD-002.**

## 11. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| SME review portal availability outage | High | Low | Redundant PostgreSQL, CDN for static assets, graceful degradation |
| Review link leakage / unauthorized access | High | Low | NanoID provides sufficient entropy; HTTPS only; optional IP whitelisting |
| SME claim adjustment discrepancies | Medium | Medium | Clear UI with transcript excerpts; audit trail of all changes; training docs |
| Data residency / compliance violation | High | Low | Deploy to Australian region; call recordings in AU; document retention policy |
| Framework definition data becomes stale | Medium | Low | Versioning via `framework_type` metadata; annual review cycle planned |

**Interview-level risks (voice pipeline, LLM hallucination, candidate refusal) are in PRD-002.**

## 12. Phased Delivery Plan

| Phase | Name | Scope |
|-------|------|-------|
| **Phase 1** | Foundation & Monorepo Scaffold | Project structure, CI/CD skeleton, database schema, shared types |
| **Phase 2** | Basic Voice Engine & Call Tracking | Daily PSTN dial-out, call status tracking, admin dashboard (no assessment logic) |
| **Phase 3** | Infrastructure Deployment (Sydney) | AWS/Azure setup, CI/CD pipeline, database init, containerization, monitoring |
| **Phase 4** | Assessment Workflow & Interjection | SFIA flow states (discovery → evidence → summary), interjection rule, transcript persistence |
| **Phase 5** | RAG Knowledge Base | pgvector setup, SFIA data ingestion, SkillRetriever, dynamic prompt injection |
| **Phase 6** | Claim Extraction Pipeline | Post-call LLM processing, claim mapping, confidence scoring, report generation |
| **Phase 7** | SME Review Portal | Next.js frontend, review UI, claim approval/adjustment workflow |
| **Phase 8** | Final Integration & Optimisation | End-to-end testing, latency tuning, audit logging, observability, production readiness |

## 13. Out of Scope (v1)

- Alternative frameworks (TOGAF, ITIL) — SFIA 9 only in v1, but architecture supports others via metadata.
- Inbound calls (candidate-initiated); administrator-triggered only.
- Mobile app for candidates.
- Multi-language support (English only).
- SSO / enterprise identity integration.
- Real-time claim extraction (see PRD-002 for scope).

## 14. Open Questions

1. **STT/TTS provider selection**: Deepgram, Google Cloud Speech, or Azure? Need latency benchmarks for AU region. (See PRD-002 for details.)
2. **Daily pricing model**: Per-minute costs for PSTN dial-out to AU numbers — need commercial review. (See PRD-002 for details.)
3. **SFIA licensing**: Are SFIA 9 skill definitions freely redistributable, or do we need a license from the SFIA Foundation? (See PRD-002 for details.)
4. **Data retention policy**: What is the regulatory requirement for call recordings in AU? (See PRD-002 for details.)
5. **SME notification channel**: Email only, or also Slack/Teams webhook?

---

## 15. Revision History

| Date | Change | Author |
|------|--------|--------|
| 2026-04-18 | Refactored PRD-001 to focus on platform/SME review; moved interview details to PRD-002 | AI Skills Assessor Team |
| 2026-04-16 | Initial draft | AI Skills Assessor Team |

---

## 16. Related Documents

- **PRD-002**: Assessment Interview Workflow — Details of voice interview, claim extraction pipeline, and technical architecture.
- **Phase 1–8**: Phased delivery plan (see Section 12).
- **ADR-001**: Hexagonal Architecture — System design pattern.
- **ADR-003**: Monorepo Structure — Repository organization.
