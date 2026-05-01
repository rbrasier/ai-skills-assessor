# PRD-001: Voice-AI SFIA Skills Assessment Platform

## Status
Approved

## Date
2026-05-01 (Last Updated)

## Document Owner
AI Skills Assessor Team

## References
- **ADR-001**: Hexagonal Architecture (Ports & Adapters)
- **ADR-004**: Voice Engine Technology (Pipecat, Daily, FastAPI)
- **ADR-005**: RAG & Vector Store Strategy (pgvector, framework-agnostic chunking)
- **PRD-002**: Assessment Interview Workflow (interview phases, claim extraction, post-call pipeline)
- **Phase 2**: Basic Voice Engine & Call Tracking (source of truth for candidate intake form, call state labels, data model)

---

## 1. Executive Summary

The Voice-AI Skills Assessment Platform is an automated system that conducts skills assessments via phone call and produces structured reports for Subject Matter Expert (SME) review.

**High-level workflow:**
1. Candidate completes a self-service intake form (name, email, employee ID, phone number).
2. System places an outbound call to the candidate via Daily PSTN gateway.
3. An AI bot conducts a structured interview with the candidate (see PRD-002 for interview details).
4. Post-call, the system extracts verifiable work claims and maps them to framework skills.
5. SME receives a structured report and review portal to approve, adjust, or reject claims.
6. Final assessment is signed off and stored.

**Intake Model**: **Candidate self-service** — candidates initiate assessments by completing an online intake form and providing their phone number. The system dials them at the number they provided. Administrators can monitor call status via a read-only dashboard.

**Framework Support**: SFIA 9 in v1. Extensible design via `framework_type` metadata in database supports future frameworks (TOGAF, ITIL, etc.) without schema changes.

**Geographic Focus**: Australian market optimised for +61 phone numbers. Infrastructure deployed to `ap-southeast-2` (Sydney region).

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
| **Administrator** | HR/L&D staff managing assessments | Read-only monitoring of call status and history, access to completed reports |

## 4. Core User Journeys

### 4.1 Assessment Initiation (Candidate Self-Service)
1. Candidate visits the assessment portal (`/`) and completes the intake form with these mandatory fields:
   - **FIRST NAME** (text)
   - **LAST NAME** (text)
   - **WORK EMAIL** (email format; unique identifier for candidate record)
   - **EMPLOYEE ID** (text; stored in candidate metadata for organisational matching)
   - **PHONE NUMBER** (international format accepted, e.g., +44 7700 900118 or 44 1234 567890)
2. System creates or retrieves Candidate record (keyed by WORK EMAIL), stores EMPLOYEE ID in metadata, then creates an AssessmentSession.
3. The voice engine initiates an outbound call to the candidate's phone number via Daily PSTN gateway (ap-southeast-2 Sydney region).
4. Candidate sees real-time call state transitions on the same page:
   - **Dialling**: "Your phone should ring in a moment. Answer when it does — caller ID will show Resonant · Noa."
   - **Call In Progress**: Waveform animation, timer (HH:MM), "Relax and speak naturally. Noa will guide the conversation."
   - **Interview Complete**: Checkmark, "Thank you for the assessment. You'll hear back by email within 2 working days."
   - **Failed**: Error state with failure reason (if available)
5. Administrators can monitor call history and status via a read-only admin dashboard (not for triggering calls).

**Note:** Calls are **candidate-initiated via the self-service form**, not administrator-triggered. Administrators can only view and monitor calls; they cannot initiate assessments for candidates.

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
2. Transcript is processed with **timestamps (mm:ss format) and speaker labels** for each transcribed line, enabling precise evidence referencing.
3. Each claim is mapped to a framework skill and responsibility level with a confidence score.
4. Claims are grouped into a structured report, ready for SME review.
5. **Two** unique review links (NanoID-based) are generated for Phase 7: one for the **SME / subject matter expert** and one for the **supervisor** — separate URLs with isolated capabilities (see Phase 7).

_For detailed extraction pipeline, see PRD-002: Assessment Interview Workflow._

### 4.4 Expert & Supervisor Review (Human reviewers)

Human review is split into **two roles**. Each receives their **own** NanoID URL (no shared token). The UI is the **assessment modal** pattern only (same structure as `frontend/public/admin.html` modal); reviewers do **not** see the operator admin dashboard chrome.

**Expert (SME):**

1. Expert receives a unique, secure link (`/review/expert/{token}`).
2. Link opens the modal showing candidate summary, AI narrative summary, SFIA competency breakdown (claims register), and transcript — **read-only** except SFIA level endorsement/adjustment per row.
3. Expert sets the endorsed or adjusted SFIA level (1–7) per claim row.
4. On **Save**, the expert enters **full name** and **work email**; the system stores these with the submission for audit.

**Supervisor:**

1. Supervisor receives a **different** unique, secure link (`/review/supervisor/{token}`).
2. Same modal layout; content is **read-only** except **verify** or **reject** per claims-register row and a **comment on every row** (including verified rows).
3. On **Save**, the supervisor enters **full name** and **work email**; the system stores these for audit.

**Final outcome:**

The assessment proceeds to the **final outcome** state (HR/export-eligible) only after **both** the expert submission **and** the supervisor submission have completed successfully. Completion order is not prescribed unless a future phase adds dependencies.

## 5. System Architecture Overview

### 5.1 Monorepo Structure

```
ai-skills-assessor/
├── apps/
│   ├── web/                          ← Next.js frontend (Tailwind, Lucide-React)
│   │   ├── app/                      ← App Router
│   │   │   ├── (dashboard)/          ← Admin dashboard routes (operators)
│   │   │   ├── (review-expert)/      ← SME/expert modal-only routes
│   │   │   ├── (review-supervisor)/  ← Supervisor modal-only routes
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
Candidate Portal       Voice Engine           Claim Extraction      Expert Modal      Supervisor Modal
       │                    │                       │                   │                   │
       ├─ Intake / dial ───>│                       │                   │                   │
       │                    ├─ Interview ──────────>│                   │                   │
       │                    │  (transcript +        │                   │                   │
       │                    │   claims extracted)   │                   │                   │
       │<─ Call Status ─────┤                       │                   │                   │
       │                    │                       ├─ Report Ready ────┼──────────────────>│
       │                    │                       │                   │                   │
       │                    │                       │         Expert: level endorse/adjust   │
       │                    │                       │<──────────────────┤                   │
       │                    │                       │                   │   Supervisor:     │
       │                    │                       │                   │   verify/reject   │
       │                    │                       │<──────────────────────────────────────┤
       │                    │                       │ Final outcome after BOTH complete      │
```

Administrators **monitor** sessions via a read-only dashboard; they **do not** trigger outbound calls (candidate self-service only — §4.1).

**Voice engine details and architecture are in PRD-002.**

## 6. Key Platform Decisions

### 6.1 Review Links: Dual NanoIDs (Expert + Supervisor)
- Each assessment report receives **two** NanoID-based URLs — **expert** (`/review/expert/{token}`) and **supervisor** (`/review/supervisor/{token}`).
- Tokens are **not interchangeable**: each URL exposes only the actions allowed for that role (capability isolation enforced server-side).
- NanoID provides URL-safe, collision-resistant, non-sequential identifiers.
- Links expire after 30 days by default (configurable).
- No PII in URLs; access is knowledge-of-token; reviewers **declare** full name + email **at submit** for audit trail.

### 6.2 Framework-Agnostic Data Model (Extensibility for v2+)
- **SFIA 9 in v1**: v1 focuses on SFIA 9 only.
- **Future framework support**: AssessmentSession and Claim entities store `framework_type` metadata (e.g., "sfia-9", "togaf-2024", "itil-4").
- **No schema migrations needed**: To add a new framework:
  1. Load framework definitions (skill codes, levels, descriptions) into the `FrameworkDefinition` table in PostgreSQL via seed script (Phase 5 RAG knowledge base).
  2. Create vectors via pgvector embedding (one vector per skill + level combination).
  3. Update assessment intake form to allow framework selection (UI change only).
  4. Existing claim extraction and SME review logic works unchanged (generic responsibility levels 1–7).
- **No hard-coded framework knowledge** in code; all framework context lives in the database and is retrieved via RAG (see ADR-005).

### 6.3 Voice Interview & Claim Extraction Pipeline
- Interviews are conducted via phone (see PRD-002 for technical details).
- Calls recorded in Daily cloud storage indefinitely.
- Claims are extracted post-call using LLM analysis of the transcript (within 5 minutes).
- Each claim includes:
  - Verbatim quote from transcript
  - Interpreted claim text
  - Framework skill code and responsibility level
  - Confidence score (0.0–1.0); **Expert** endorses/adjusts SFIA levels; **Supervisor** verifies/rejects the claims register with comments (Phase 7)
  - Evidence segments (timestamp ranges in transcript supporting the claim)
- Claims are verified against the framework definition via pgvector RAG (relevant skill context injected into extraction prompt).

**For voice engine architecture and technical decisions (Pipecat, Daily, Claude, pgvector), see PRD-002: Assessment Interview Workflow and ADR-005: RAG & Vector Store Strategy.**

## 7. Non-Functional Requirements

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| **Call Setup Latency** | < 5 seconds from dial to candidate answer | Call must feel immediate |
| **Call Round-Trip Latency** | < 500ms (Sydney region) | Natural conversation feel |
| **Claim Extraction Processing** | < 5 minutes post-call | Fast turnaround for SME review |
| **Concurrent Calls** | 10+ simultaneous | Enterprise pilot scale |
| **Availability** | 99.5% uptime during business hours (AEST) | Reliability for assessments |
| **Data Residency** | Australian region (Sydney ap-southeast-2) | Compliance with data sovereignty expectations |
| **Call Recording Storage** | Stored indefinitely in Daily cloud storage | Audit trail and regulatory compliance |
| **Transcript Retention** | Full STT transcripts retained indefinitely (post-call analysis) | Audit trail and quality assurance |
| **Security** | TLS everywhere, review links with NanoID (non-sequential, non-guessable), no PII in URLs | Data protection |

## 8. Data Model (Platform Level)

### Core Entities

| Entity | Purpose | Key Fields |
|--------|---------|-----------|
| **Candidate** | Person being assessed | `email` (unique identifier), `first_name`, `last_name`, `metadata` (JSON: {`employee_id`, ...}), `created_at` |
| **AssessmentSession** | Single assessment call | `id`, `candidate_email` (FK), `phone_number`, `status` (pending/dialling/in_progress/completed/failed/cancelled), `metadata` (JSON: {`failureReason`, `cancelledAt`, ...}), `recording_url` (Daily cloud), `transcript_url` (structured transcript with speaker labels & timestamps), `started_at`, `ended_at`, `created_at` |
| **AssessmentTranscript** | Full call transcript with metadata | `id`, `session_id` (FK), `raw_transcript` (JSON array of timestamped, speaker-labeled lines), `generated_at` |
| **AssessmentReport** | Output of assessment + dual human review | `session_id`, `expert_review_token`, `supervisor_review_token`, `report_status` (workflow includes awaiting expert/supervisor and reviews complete), `report_generated_at`, expert/supervisor reviewer identity + submitted timestamps, `reviews_completed_at` when both are done |

### Transcript Structure

All transcripts include **speaker labels** and **timestamps (mm:ss format)** for each line to enable precise evidence referencing and claim attribution:

```json
{
  "session_id": "abc123",
  "transcript": [
    {
      "timestamp": "00:12",
      "speaker": "bot",
      "speaker_name": "Noa",
      "text": "Hi, I'm Noa. Can you hear me clearly?"
    },
    {
      "timestamp": "00:15",
      "speaker": "candidate",
      "speaker_name": "Candidate",
      "text": "Yes, I can hear you fine."
    },
    {
      "timestamp": "00:18",
      "speaker": "bot",
      "speaker_name": "Noa",
      "text": "Great. Let's start with your background..."
    }
  ]
}
```

**Transcript fields:**
- `timestamp`: Format `mm:ss` indicating position in the call
- `speaker`: `"bot"` (AI bot) or `"candidate"` (the person being assessed)
- `speaker_name`: Human-readable name ("Noa" for bot, candidate's name if available)
- `text`: Verbatim transcribed text from STT output

**Usage in claim extraction:**
- Claims reference transcript segments by timestamp ranges (e.g., "00:45–01:12") for SME verification
- Speaker label ensures clarity on who said what during evidence gathering
- Timestamps enable quick navigation to relevant portions in recorded call

**Notes:**
- **Candidate.email** is the unique identifier (natural key) for linking intake forms to sessions.
- **Candidate.metadata** JSON field stores extensible data like `employee_id`, `organisation_id`, etc.
- **AssessmentSession.metadata** JSON field stores optional state: failure reasons, cancellation timestamps, etc.
- **AssessmentSession.recording_url** points to Daily's indefinite cloud storage. Retrieval happens at claim extraction time.
- **AssessmentTranscript** entity stores the structured, speaker-labeled transcript with timestamps; generated post-call via STT processing.
- **Detailed data structures for interviews, claims, and framework definitions are in PRD-002.**

## 9. Platform Integration Points

| System | Integration | Purpose |
|--------|-------------|---------|
| **Email / Notification System** | Send review links | Expert **and** supervisor invitations (two URLs); reminders |
| **PostgreSQL** | Persistent data store | Candidates, sessions, reports |
| **NanoID** | Access control for review modals | Two independent tokens per report; links expire in 30 days (configurable) |

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
| SME review portal availability outage | High | Low | Redundant PostgreSQL (ap-southeast-2 region), CDN for static assets, graceful degradation (read-only fallback if API down) |
| Review link leakage / unauthorized access | High | Low | NanoID provides sufficient entropy (non-guessable, non-sequential); HTTPS only; links expire in 30 days; optional IP whitelisting |
| SME claim adjustment discrepancies | Medium | Medium | Clear UI with verbatim transcript excerpts; audit trail of all SME changes; training docs for consistency |
| Data residency / compliance violation | High | Low | **Mandatory deployment to ap-southeast-2 (Sydney)**; call recordings stored in Daily Sydney region indefinitely; compliance review required before Phase 3 |
| Framework definition data becomes stale | Medium | Low | Versioning via `framework_type` + `framework_ver` metadata in pgvector; annual review + re-embedding cycle; v2 gate for new frameworks |
| SFIA content licensing issue | High | Medium | **BLOCKING RISK**: Must resolve licensing before Phase 5 RAG knowledge base start. Mitigation: If SFIA definitions restricted, implement framework lookup API + manual entry instead of pgvector embeddings. |

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

- **Alternative frameworks** — SFIA 9 only in v1. Architecture supports TOGAF, ITIL, etc. via `framework_type` metadata without schema changes. Multi-framework support deferred to v2.
- **Inbound calls** — Candidates do not receive inbound links; only outbound calls initiated by the system after intake form submission.
- **Mobile app** — Web portal only (responsive design for mobile browsers).
- **Multi-language support** — English only in v1.
- **SSO / enterprise identity integration** — Email-based candidate lookup only in v1.
- **Real-time claim extraction** — Claims extracted post-call (asynchronous); not during the call (see PRD-002 for details).
- **Admin call initiation** — Admins cannot trigger calls directly; candidates self-service only. Admins can only monitor via read-only dashboard.

## 14. Open Questions

| Question | Owner | Deadline | Impact | Mitigation |
|----------|-------|----------|--------|-----------|
| **STT/TTS provider selection** | Tech Lead | Before Phase 3 | Phase 3 replaces stub implementations | Phase 2 uses hardcoded responses. If no provider selected by Phase 3 start, defer to Phase 4. |
| **Daily pricing model** | Product / Finance | Before Phase 2 end | May impact go/no-go for production | Daily pricing is fixed regardless of decision; captured as operational cost. Does not block implementation. |
| **SFIA 9 licensing** | Legal / Product | Before Phase 5 start | **Blocks Phase 5 RAG knowledge base if restrictions apply** | Must resolve before ingesting SFIA definitions into pgvector. If SFIA content is restricted, implement framework lookup API instead of embedding. |
| **Data retention policy (call recordings)** | Legal / Compliance | Before Phase 3 end | Affects deletion/archival process | Phase 2–4 store indefinitely in Daily cloud. Phase 5+ can implement retention policy if required. Does not block v1 release. |
| **SME notification channel** | Product | Before Phase 7 | Phase 7 SME portal design | Default: email only in v1. Slack/Teams integrations deferred to v2. Does not block Phase 7 release. |
| **Authentication for SME portal** | Tech Lead | Before Phase 7 start | Phase 7 expert/supervisor modal security | **Decision: Unauthenticated NanoID-based links** (no login required). **Two** independent tokens per report (expert vs supervisor). Links expire in 30 days (configurable). Reviewers declare full name + email at submit for audit. Optional: IP whitelisting for additional security. |

---

## 15. Revision History

| Date | Change | Author |
|------|--------|--------|
| 2026-05-01 | **Dual human review**: Replaced single SME review flow with **expert** + **supervisor** NanoID URLs, modal-only UI (aligned with Phase 7), final outcome after **both** submissions; updated §5.2 data flow (removed admin trigger path), §6.1 dual tokens, data model `AssessmentReport` row, §9 integration table, Open Questions authentication row. | AI Skills Assessor Team |
| 2026-04-20 | **Refinement via /doc-refiner**: Align with Phase 2 as source of truth. (1) Clarified **candidate self-service intake form is primary flow** (not admin-triggered). (2) Fixed intake form fields: FIRST NAME, LAST NAME, WORK EMAIL, EMPLOYEE ID, PHONE NUMBER (all mandatory; employee ID stored in metadata). (3) Specified call state labels from Phase 2 design: Dialling, Call In Progress, Interview Complete, Failed, Cancelled. (4) Clarified call recording storage: **indefinite retention in Daily cloud** (not 12 months). (5) Updated data model: Candidate keyed by email, metadata JSON for employee_id, AssessmentSession with phone_number and metadata JSON fields. (6) Expanded "Framework-Agnostic" section to clarify: SFIA 9 only in v1; future frameworks via `framework_type` metadata tag + pgvector + no schema migrations. (7) Converted Open Questions to structured table with owner, deadline, impact, mitigation. (8) Added explicit decision: **SME portal uses unauthenticated NanoID links** (no login required). (9) Added authentication clarification: not needed for v1. (10) Clarified phase sequencing: SFIA licensing question must be resolved before Phase 5 RAG start (blocks framework definition ingestion). | AI Skills Assessor Team |
| 2026-04-18 | Refactored PRD-001 to focus on platform/SME review; moved interview details to PRD-002 | AI Skills Assessor Team |
| 2026-04-16 | Initial draft | AI Skills Assessor Team |

---

## 16. Related Documents

- **PRD-002**: Assessment Interview Workflow — Details of voice interview, claim extraction pipeline, and technical architecture.
- **Phase 2: Basic Voice Engine & Call Tracking** — **SOURCE OF TRUTH** for candidate intake form design, call state labels, database schema, and API endpoints.
- **Phase 1–8**: Phased delivery plan (see Section 12 and `/docs/development/to-be-implemented/`).
- **ADR-001**: Hexagonal Architecture — System design pattern.
- **ADR-004**: Voice Engine Technology — Pipecat + Daily + FastAPI decisions.
- **ADR-005**: RAG & Vector Store Strategy — pgvector chunking, framework-agnostic metadata, future extensibility.
