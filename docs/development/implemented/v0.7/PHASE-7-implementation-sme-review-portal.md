# PHASE-7 Implementation: SME Review Portal

## Reference
- **Phase Document:** `docs/development/implemented/v0.7/v0.7-phase-7-sme-review-portal.md`
- **Implementation Date:** 2026-05-01
- **Status:** In Progress

---

## Verification Record

### PRDs Approved
| PRD | Title | Status | Verified |
|-----|-------|--------|---------|
| PRD-001 | Voice-AI Skills Assessment Platform | Approved | 2026-05-01 |
| PRD-002 | Assessment Interview Workflow | 🟢 Approved | 2026-05-01 |

### ADRs Accepted
| ADR | Title | Status | Verified |
|-----|-------|--------|---------|
| ADR-001 | Hexagonal Architecture | Accepted | 2026-05-01 |
| ADR-004 | Voice Engine Technology | Accepted | 2026-05-01 |

All documents approved. Version bumped to 0.7.0.

---

## Phase Summary

Build the Next.js SME review portal delivering two surfaces: expert and supervisor token-URL review flows (modal-only, no admin chrome) and a full operator admin dashboard mirroring `frontend/public/admin.html` with sidebar, stats, charts, and assessments table.

---

## Phase Scope

### Deliverables
- Expert token route `/review/expert/[token]` — full-viewport modal, per-claim SFIA level endorsement/adjustment, reviewer identity capture
- Supervisor token route `/review/supervisor/[token]` — full-viewport modal, per-claim verify/reject + optional comment, reviewer identity capture
- Operator admin dashboard `/dashboard` — full `admin.html` shell parity: sidebar, topbar, stats row, bar chart, donut chart, assessments table with search/filter
- Shared `AssessmentReviewModal` with `variant: "expert" | "supervisor" | "operator-read-only"`
- Operator auth: login page + middleware using `ADMIN_TOKEN` env var
- Extended admin sessions API: enriched session summaries including candidate name, report status, top skills, max SFIA level, confidence
- New Next.js API proxy routes for review and admin endpoints

### External Dependencies
- Phase 6 claim extraction pipeline (implemented v0.6) — `claims_json`, `transcript_json`, dual review tokens
- `frontend/public/admin.html` — canonical design reference
- Backend: `GET/PUT /api/v1/review/expert/{token}` and `GET/PUT /api/v1/review/supervisor/{token}` (Phase 6)

---

## Implementation Strategy

### Approach
Build in strict dependency order: types → API routes → CSS → components → pages.
Expert and supervisor routes can be parallelized once the shared modal component is complete.

### Build Sequence
1. Shared types (Claim, AssessmentReport, review payloads) in `packages/shared-types`
2. Python backend: extend `GET /api/v1/admin/sessions` with enriched fields
3. Next.js API proxy routes (review/expert, review/supervisor)
4. Admin CSS additions to `globals.css`
5. Shared `AssessmentReviewModal` and sub-components
6. Admin shell components (sidebar, topbar, stats, charts, table)
7. Dashboard page rewrite + auth layout
8. Expert + supervisor review pages
9. Login page + `middleware.ts` for auth guard

---

## Known Risks and Unknowns

### Risks
- Phase 6 dual-token fields may not be populated in all sessions (only sessions processed post-Phase 6): handled by graceful null checks in UI
- Admin sessions enrichment requires SQL changes to return claims summary: solved by extending `list_admin_session_summaries` in persistence layer

### Unknowns
- Chart data aggregation (calls per day, outcomes donut) requires date-bucketing query: implemented server-side in a new `/api/admin/stats` endpoint

### Scope Clarifications
No deviations from phase document. WCAG AA deferred to Phase 8 as documented.

---

## Implementation Notes

### Part 1: Shared Types
- **Goal:** Add `Claim`, `AssessmentReport`, `ExpertReviewPayload`, `SupervisorReviewPayload` to `packages/shared-types`
- **Acceptance criteria:** TypeScript compiles; web app can import these types
- **Key decisions going in:**
  - Claim fields use camelCase in TypeScript, mapped from snake_case API responses
  - `supervisorComment` is optional on both SupervisorReviewClaimItem and stored claim

### Part 2: Backend Admin Enrichment
- **Goal:** Extend `GET /api/v1/admin/sessions` to return `candidate_name`, `report_status`, review tokens, `max_sfia_level`, `overall_confidence`, `top_skill_codes`
- **Acceptance criteria:** Admin dashboard table rows show skill pills and SFIA level from API
- **Key decisions going in:**
  - New `list_admin_session_summaries` method on `IPersistence` avoids touching domain model
  - SQL query joins sessions with claims_json JSONB for derived aggregates

### Part 3: API Proxy Routes
- **Goal:** Next.js routes proxy to voice engine for review endpoints; admin/stats derived from sessions
- **Acceptance criteria:** `GET/PUT /api/review/expert/[token]` proxies correctly; 409 on re-submit surfaces as error

### Part 4: Admin Dashboard
- **Goal:** `/dashboard` renders full `admin.html` shell with live data
- **Acceptance criteria:** Sidebar, topbar, stats row, bar+donut charts, assessments table — all wired to real API data

### Part 5: Expert Review Route
- **Goal:** `/review/expert/[token]` renders modal-only, full-viewport; per-claim level selection; identity form; 409 guard
- **Acceptance criteria:** Phase 7 acceptance criteria §Expert Token Route

### Part 6: Supervisor Review Route
- **Goal:** `/review/supervisor/[token]` renders modal-only; per-claim verify/reject + comment; identity form; 409 guard
- **Acceptance criteria:** Phase 7 acceptance criteria §Supervisor Token Route

---

## Decisions Log

| Date | Part | Decision | Rationale | Files Affected |
|------|------|----------|-----------|----------------|
| 2026-05-01 | — | Initial implementation plan created | — | This document |
| 2026-05-01 | Part 2 | New `list_admin_session_summaries` method on IPersistence instead of extending domain model | Keeps domain model clean; admin listing is a read-only projection | `domain/ports/persistence.py`, `adapters/postgres_persistence.py`, `adapters/in_memory_persistence.py` |
| 2026-05-01 | Part 3 | Auth via HttpOnly cookie set on `/api/auth/login`; `middleware.ts` checks cookie | Stateless, works with Next.js Edge runtime; no session DB needed for MVP | `apps/web/src/middleware.ts`, `apps/web/src/app/api/auth/login/route.ts` |
| 2026-05-01 | Part 4 | Charts built with inline SVG/path (no charting library) | Matches admin.html approach; zero bundle cost; sufficient for MVP data volumes | `components/admin-shell/CallsBarChart.tsx`, `OutcomesDonut.tsx` |
| 2026-05-01 | All | CSS classes copied from admin.html into globals.css, used directly in JSX | Fastest path to design fidelity; Tailwind utilities supplement for layout | `apps/web/src/app/globals.css` |

---

## Revision History

| Date | Revision | Summary | Status |
|------|----------|---------|--------|
| 2026-05-01 | — | Initial implementation plan | In Progress |

---

## Related Documents
- Phase: `docs/development/implemented/v0.7/v0.7-phase-7-sme-review-portal.md`
- PRD-001: `docs/development/prd/PRD-001-voice-ai-sfia-assessment-platform.md`
- PRD-002: `docs/development/prd/PRD-002-assessment-interview-workflow.md`
- ADR-001: `docs/development/adr/ADR-001-hexagonal-architecture.md`
- ADR-004: `docs/development/adr/ADR-004-voice-engine-technology.md`
- Contract: `docs/development/contracts/assessment-report-contract.md`
