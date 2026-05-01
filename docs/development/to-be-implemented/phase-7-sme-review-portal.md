# Phase 7: Expert & Supervisor Review (Next.js Frontend)

## Status
To Be Implemented

## Date
2026-05-01

## References
- PRD-001: Voice-AI Skills Assessment Platform (candidate self-service intake; read-only admin monitoring)
- PRD-002: Assessment Interview Workflow (post-call report shape)
- ADR-001: Hexagonal Architecture (UI is presentation + API orchestration only)
- ADR-004: Voice Engine Technology (FastAPI voice engine owns persistence in the current plan)
- [Assessment Report Contract](../contracts/assessment-report-contract.md): canonical dual-review payloads and claim shapes
- [Phase 6 revision: dual review tokens](phase-6-revision-dual-review-tokens.md): backend deltas on top of baseline Phase 6 (single-token pipeline)
- **UI reference:** [`frontend/public/admin.html`](../../../frontend/public/admin.html)
  - **Token routes** (`/review/expert/*`, `/review/supervisor/*`): **modal only** — `.modal-overlay` / `.modal` (experts/supervisors **must not** see sidebar, stats, charts, or main table).
  - **Operator dashboard** (`/dashboard/*`): **full page parity** with `admin.html` — `.shell` layout (sidebar + main), topbar, stats row, charts row, assessments table; row click opens the **same** assessment detail modal component (read-only for operators unless product adds actions later).
- Phase 4 ([implemented](../implemented/v0.5/PHASE-4-implementation-assessment-workflow.md)): structured `transcript_json` (turns, timestamps, phases) for the transcript panel
- Phase 5 ([implemented](../implemented/v0.5/PHASE-5-implementation-rag-knowledge-base.md)): SFIA skill definitions used when enriching claims (skill names/descriptors in breakdown rows)
- Phase 6: Claim Extraction Pipeline — baseline delivers `claims_json`, transcript column, single `review_token` + `GET /review/{token}`; **dual-token APIs** require [phase-6-revision-dual-review-tokens.md](phase-6-revision-dual-review-tokens.md) (see §0)

**Cross-document note:** PRD-001 §5.2 data flow reflects candidate self-service (no admin-triggered dial).

---

## Objective

Build Next.js UI in two surfaces, both styled from **`frontend/public/admin.html`**:

1. **Expert & supervisor token URLs** — Full-viewport **modal only** (same sections as the mock modal): candidates endorse/adjust levels or verify/reject + comment; identity at save (see role table below).

2. **Operator admin dashboard** (`/dashboard/*`) — **Mirror the rest of `admin.html`**: sidebar navigation, topbar (including link back to candidate portal `/`), stats cards, charts row (calls per day + outcomes donut), and **All assessments** table with search/filter; opening a row shows the **same** modal component used on token routes, in **operator read-only** mode (no expert/supervisor edit controls unless explicitly added later).

**Final outcome:** The assessment **does not** move to the terminal **final outcome** state until **both** the SME save **and** the supervisor save have succeeded. Order does not matter unless product later defines dependencies.

| Reviewer | URL pattern (example) | Chrome | May edit | Must collect on save |
|----------|----------------------|--------|----------|----------------------|
| **SME (subject matter expert)** | `/review/expert/[token]` | Modal only | Per claim: endorse/adjust SFIA level **1–7** | Full name, work email |
| **Supervisor** | `/review/supervisor/[token]` | Modal only | Per claim: verify/reject + **comment** (every row) | Full name, work email |
| **Operator** | `/dashboard/...` | Full `admin.html` shell | Monitoring only (no call trigger); optional copy expert/supervisor links | N/A (authenticated dashboard — auth mechanism as per Phase 1/product) |

---

## 0. Prerequisites

**Baseline Phase 6** ([phase-6-claim-extraction-pipeline.md](phase-6-claim-extraction-pipeline.md)) produces `claims_json`, transcript storage, and a single SME review token. The **expert + supervisor** modal URLs require the incremental backend spec [phase-6-revision-dual-review-tokens.md](phase-6-revision-dual-review-tokens.md) (dual NanoIDs, `GET`/`PUT` per role, session audit columns). Implement that revision before shipping Phase 7, or in parallel if both streams share one release.

Payload shapes and enums are **normative** in [Assessment Report Contract](../contracts/assessment-report-contract.md).

**Rule:** Expert token cannot write supervisor fields and vice versa (server-enforced).

---

## 1. Deliverables

### 1.1 Application layout

**Tech stack:** Next.js 14+ App Router, Tailwind — map **all** `:root` tokens from `admin.html` (`--paper`, `--ink`, `--accent`, `--line`, status colours, fonts Inter Tight / Instrument Serif / JetBrains Mono). Lucide icons optional (mock uses inline SVG).

**Route structure:**

```
packages/web/src/app/
├── layout.tsx
├── page.tsx                                    ← Candidate portal (Phase 2) — unchanged
├── (dashboard)/                                ← Mirrors full admin.html shell (§1.4)
│   ├── layout.tsx                              ← .shell: sidebar + main wrapper
│   └── dashboard/
│       └── page.tsx                            ← GET /dashboard — overview matching mock
├── (review-expert)/
│   └── review/
│       └── expert/
│           └── [token]/
│               ├── layout.tsx                  ← No sidebar: full-viewport modal host
│               └── page.tsx
├── (review-supervisor)/
│   └── review/
│       └── supervisor/
│           └── [token]/
│               ├── layout.tsx
│               └── page.tsx
└── api/                                        ← Proxies as needed
```

**Layout rules:**

- **`/review/expert/*` and `/review/supervisor/*`:** Render **only** the modal host (equivalent to `#modalOverlay` + `#modal`). **Do not** mount `.shell`, sidebar, stats, or main table.
- **`/dashboard/*`:** Render the **full** `.shell` grid from `admin.html` (sidebar | main). Reuse shared tokens (`--paper`, `--ink`, `--accent`, fonts).

### 1.2 Modal UI parity (`frontend/public/admin.html`)

Port the **modal** sections to React components so behaviour matches the mock:

| Mock section | Maps to data (Phase 4–6) |
|--------------|---------------------------|
| `.modal-header` — avatar, name, facts | `candidate_name`, session date/time/duration, work email from candidate/session API |
| Score strip (`.score-strip` / `.score-cell`) | Derived: **original** max SFIA level from AI extraction, **current** max level after all reviews (supervisor rejections reduce this), avg confidence, skill count, duration, provisional outcome label. Shows both for transparency. |
| `.summary-box` — AI-generated summary | Phase 6 narrative / exec summary field on report. If absent, show greyed-out placeholder box: "Summary will appear here once AI processing completes" |
| `.skills-table` — `.skill-detail-row` | **One row per claim** in `claims_json`: skill name/code, descriptor (from Phase 5 definition or claim text), evidence quote + transcript time ref (mm:ss format), level ladder, confidence bar |
| `.transcript-section` | `transcript_json` from Phase 4 — speaker labels, timestamps, optional evidence tags |

**Role-specific controls (sticky footer):**

- **Expert:** Per row: level control (endorse AI level vs select adjusted 1–7). Primary **Save** button (sticky footer) opens or precedes a step collecting **full name** + **email** (validate email format), then submits. Button disabled after first successful submission.
- **Supervisor:** Per row: **Verify** or **Reject** + **optional comment**. **Save** button (sticky footer) collects **full name** + **email**, then submits. Comments are optional for both verify and reject decisions. Button disabled after first successful submission.

All header actions in the static mock (**Export PDF**, **Approve**) are **hidden or disabled** on expert/supervisor routes unless product adds operator-only workflow later. On **dashboard** modal open, **Approve** / **Export PDF** remain **non-functional placeholders** until a later phase defines APIs — or hide them for parity without implying behaviour.

### 1.3 Admin shell parity (`frontend/public/admin.html`)

Port the **non-modal** chrome so `/dashboard` matches the mock:

| Mock region | Behaviour |
|-------------|-----------|
| `.shell` | CSS grid: sidebar (220px) + main |
| `.sidebar` | Brand, nav groups (Analytics: Dashboard, Candidates; Configuration: Skills library, Settings — labels may stay placeholder until those routes exist), user chip (from auth/session or config) |
| `.main` `.topbar` | Title (“Assessment Overview”), **Candidate portal** primary button → `/` |
| `.page` `.page-head` | Title + subtitle (derive counts from API: completed calls, awaiting review, last call) |
| `#statsRow` `.stats` | Stat cards — wire real aggregates from Phase 7 endpoints; **Awaiting review** card shows report-count metrics |
| `.charts` | Bar chart (calls per day) + donut (call outcomes) — powered by Phase 7 chart/stats endpoints |
| `.table-card` | Toolbar (filters: All / Complete / Awaiting review / Incomplete), search (name, email, skill), header row, body rows matching `.trow` grid columns |
| Row click | Opens shared **`AssessmentReviewModal`** (same component as token flows) in **`variant=”operator-read-only”`** — hide expert/supervisor edit footers; show `report_status` + **copy** actions for expert/supervisor URLs when tokens exist |

**Data & APIs:** Phase 7 creates `GET /api/v1/admin/sessions` (or equivalent) with filters (All / Complete / Awaiting review / Incomplete), search (name, email, skill), and returns session + report metadata. Phase 7 also creates endpoints for chart aggregates (calls per day, outcome buckets, stats). Pagination: server-side with limit/offset parameters.

### 1.4 Shared modal component

Use one **`AssessmentReviewModal`** (contents per §1.2) with props: `variant: "expert" | "supervisor" | "operator-read-only"`.

**Variant contract (TypeScript interface in component file):**
```typescript
interface AssessmentReviewModalProps {
  variant: "expert" | "supervisor" | "operator-read-only";
  reportId: string;
  // Underlying data shapes (expert/supervisor payloads) must conform to 
  // Assessment Report Contract §6 (ExpertReviewSubmitPayload, SupervisorReviewSubmitPayload)
}
```

Each variant renders the same read-only core (header, score strip, summary, claims table, transcript) but disables/enables controls:
- **expert**: SFIA level control per row; Save button enabled
- **supervisor**: Verify/Reject + comment per row; Save button enabled
- **operator-read-only**: No controls; all rows read-only; Save button hidden

### 1.5 Component split (suggested)

```
packages/web/src/components/
├── admin-shell/
│   ├── AdminShellLayout.tsx           ← .shell grid
│   ├── AdminSidebar.tsx
│   ├── AdminTopbar.tsx
│   ├── StatsRow.tsx
│   ├── CallsBarChart.tsx
│   ├── OutcomesDonut.tsx
│   └── AssessmentsTable.tsx           ← opens AssessmentReviewModal on row click
├── review-modal/
│   ├── AssessmentReviewModal.tsx      ← Shared modal; variant drives footer controls
│   ├── ModalHeader.tsx
│   ├── ScoreStrip.tsx
│   ├── AiSummaryPanel.tsx
│   ├── ClaimsRegisterTable.tsx
│   ├── TranscriptPanel.tsx
│   ├── ExpertClaimControls.tsx
│   ├── SupervisorClaimControls.tsx
│   └── ReviewerIdentityForm.tsx
└── ui/
```

Reuse Tailwind tokens derived from `admin.html` `:root` across **shell + modal**.

### 1.6 Security

- **Knowledge-based URLs:** Two independent NanoIDs; supervisor cannot guess expert URL without the link.
- **Capability isolation:** Server rejects cross-role field writes.
- **HTTPS**, rate limiting, no candidate PII in paths.
- **Reviewer PII:** Name and email stored on submission for audit trail (GDPR/retention policy out of scope for this doc).
- **Dashboard:** Requires **operator authentication** per product/Phase 1 (not NanoID); no exposure of expert/supervisor token URLs to unauthenticated users.

---

## 2. UI/UX requirements

- **Visual fidelity:** Match `admin.html` — **dashboard**: sidebar, stats, charts, table chrome; **modal**: typography, spacing, card radius, ladder/confidence patterns (shared tokens).
- **Responsive:** Full responsive design from **≥375px (mobile)** through desktop. 
  - Token review modals (expert/supervisor): Responsive layout on tablet (≥768px) and mobile.
  - Dashboard: Full responsive with collapsible sidebar on tablet/mobile (≥768px), hamburger menu on mobile.
- **Accessibility:** WCAG AA compliance is a **Phase 8+** item (not included in Phase 7 scope). Phase 7 ships without formal accessibility audit; Phase 8 will address dashboard, filters, modals, and token flows.
- **States:** Loading; empty table; 404/expired token; network error with retry; **already submitted** on token routes (read-only view, Save button disabled).

---

## 3. Build order (within Phase 7)

**Blocking prerequisites (must complete in sequence):**

1. Extract shared design tokens from `frontend/public/admin.html` into the Next app (Tailwind theme or CSS module).
2. Define admin sessions API contract and endpoints (`GET /api/v1/admin/sessions`, filters, chart aggregates endpoints).
3. **Shared `AssessmentReviewModal`:** Read-only core (header, score strip, summary, claims table, transcript); variant interface locked (§1.4).
4. **Admin shell layout:** Sidebar, topbar, stats row, charts, assessments table — wired to admin sessions API + chart endpoints.

**Can parallelize (steps 4–6 once above is complete):**

5. Expert token route: mount modal only + `variant="expert"` + `PUT` expert flow.
6. Supervisor token route: `variant="supervisor"` + `PUT` supervisor flow + sticky footer with comment field.
7. Dashboard row click: opens shared modal in `variant="operator-read-only"`; show copy-link UI for expert/supervisor URLs.
8. Operator login: Simple auth with env-var token (hardcoded login form, token from `ADMIN_TOKEN` env var).
9. Error states (404/expired token, already submitted, network errors) on all routes.

**Note:** Accessibility audit (WCAG AA) is Phase 8+; not included in Phase 7 scope.

---

## 4. Definition of Done

- **`/dashboard`:** Visual and structural parity with **`frontend/public/admin.html`** shell (sidebar, stats, charts, assessments table, topbar link to `/`). Data from Phase 7 admin sessions API + chart endpoints.
- **Operator authentication:** Simple login with env-var token (`ADMIN_TOKEN`); session persists until logout.
- Expert and supervisor token pages show **only** the modal surface (no admin shell, sidebar, stats, or main table).
- **`AssessmentReviewModal`** reused for operators (read-only) and both token roles; variant contract enforces capability isolation.
- Both expert/supervisor flows persist reviewer name/email and role-specific decisions server-side.
- Save button disabled immediately after first successful submission; second attempt shows "already submitted" message with no database change.
- Final outcome progression (`report_status`) occurs **only** after both expert and supervisor saves succeed.
- All validation rules (email format, SFIA level 1–7, comment length, name non-empty) enforced on both client and server.
- Types and payloads align with Assessment Report Contract §6 (ExpertReviewSubmitPayload, SupervisorReviewSubmitPayload).

---

## 5. Acceptance criteria

### Admin Dashboard

- [ ] **`GET /dashboard`** renders the **full** admin shell matching `admin.html`: `.shell` grid, sidebar brand + nav groups, topbar with **Candidate portal** → `/`, page title/subtitle, stats row, charts row, assessments table with toolbar filters + search. **Verified by:** Visual comparison with mock; manual testing on desktop/tablet/mobile.
- [ ] Table rows display (candidate name, email, date, duration, top skills, max level, confidence) from **`GET /api/v1/admin/sessions`** endpoint. **Verified by:** E2E test loading sessions and rendering rows.
- [ ] Toolbar filters (All / Complete / Awaiting review / Incomplete) and search (name, email, skill) update table in real-time. **Verified by:** E2E test filtering and searching.
- [ ] Row click opens **`AssessmentReviewModal`** in `variant="operator-read-only"` with header, score strip (both original and current max levels), summary, claims table, transcript. **Verified by:** E2E test row click → modal appearance.
- [ ] Operator modal shows **copy** buttons for **expert** and **supervisor** review URLs when both tokens exist. **Verified by:** Manual testing; verify button clicks copy URLs to clipboard.
- [ ] Operator authentication: Login page accepts token from `ADMIN_TOKEN` env var. Session persists until logout. **Verified by:** Manual test login/logout flow.

### Expert Token Route (`/review/expert/[token]`)

- [ ] Route renders **modal only** — no sidebar, stats, charts, main table, or topbar (full viewport modal host). **Verified by:** Visual inspection; DOM tree should not contain `.shell` or `.sidebar`.
- [ ] Modal shows candidate summary, score strip (original and current max levels), AI summary (or greyed-out placeholder), claims table, transcript (read-only). **Verified by:** Visual comparison with mock; manual content verification.
- [ ] Expert can **endorse** (accept AI-extracted level) or **adjust** to SFIA level **1–7** per claim row. **Verified by:** E2E test selecting different levels per row.
- [ ] **Save** button (sticky footer) disabled until expert enters **full name** and **valid email**. **Verified by:** E2E test form validation; attempt save with missing/invalid fields should fail.
- [ ] On successful save, button is immediately disabled; second attempt shows message "You have already submitted your review. No changes were made." **Verified by:** E2E test duplicate submission.
- [ ] Invalid/expired tokens show generic 404 page. **Verified by:** E2E test invalid token.

### Supervisor Token Route (`/review/supervisor/[token]`)

- [ ] Route renders **modal only** — same layout as expert (full viewport modal host, no admin shell). **Verified by:** Visual inspection; DOM structure matches expert route.
- [ ] Modal shows all expert-adjusted levels (from previous expert save) as **read-only** context. **Verified by:** Manual test after expert submits; supervisor view shows updated levels.
- [ ] Supervisor can **Verify** or **Reject** per claim row with **optional comment** (comment field optional for both actions). **Verified by:** E2E test toggling verify/reject and optional comment submission.
- [ ] **Save** button requires **full name** and **valid email**. **Verified by:** E2E test form validation.
- [ ] On successful save, button disabled; second attempt shows "You have already submitted your review." **Verified by:** E2E test duplicate submission.
- [ ] Invalid/expired tokens show generic 404. **Verified by:** E2E test invalid token.

### Shared Modal (`AssessmentReviewModal`)

- [ ] Score strip displays **original max SFIA level** (from AI extraction) and **current max level** (after all reviews). **Verified by:** E2E test renders both values correctly when expert adjusts or supervisor rejects.
- [ ] AI summary box: if summary present, shows narrative text; if absent, shows greyed-out placeholder: "Summary will appear here once AI processing completes". **Verified by:** E2E test rendering with/without summary data.
- [ ] Claims table rows show skill name/code, descriptor, evidence quote + transcript time (mm:ss format), level ladder (expert) or verify/reject + comment (supervisor), confidence bar. **Verified by:** Visual comparison; E2E test data rendering.
- [ ] Transcript section shows speaker labels, timestamps, optional evidence tags. **Verified by:** Visual inspection.

### Final Outcome State

- [ ] `report_status` field advances to **awaiting_supervisor** only after expert saves. **Verified by:** API test; query session after expert submission.
- [ ] `report_status` advances to **reviews_complete** (or final-outcome-eligible) only after **both** expert and supervisor save successfully. **Verified by:** API test querying session after both submissions.

### Validation Rules (Client & Server)

- [ ] **Email format:** Valid RFC 5322 email; reject on both client (real-time) and server (on `PUT`). **Verified by:** E2E test invalid emails bounce; server returns 400 Bad Request.
- [ ] **Full name:** Non-empty string (trim whitespace); required on both client and server. **Verified by:** E2E test empty name blocked.
- [ ] **Expert SFIA level:** Integer 1–7; reject out-of-range values. **Verified by:** E2E test submitting invalid levels.
- [ ] **Supervisor decision:** Enum (verify | reject); server rejects invalid values with 400. **Verified by:** API test direct `PUT` with invalid enum.
- [ ] **Supervisor comment:** Optional, but if provided, must be non-empty after trim. **Verified by:** E2E test submitting whitespace-only comment.
- [ ] **Already-submitted check:** Second submission by same role returns 409 Conflict (or equivalent); no duplicate database entry. **Verified by:** E2E test double-submit.

### Testing approach

- **E2E tests** (Playwright/Cypress): Admin dashboard filters/search, row click → modal, expert/supervisor form submission, duplicate submission, invalid tokens, final outcome state progression.
- **Manual testing checklist:** Visual fidelity (design token parity with `admin.html`), responsive layouts (mobile/tablet/desktop), error messages (404, already submitted, validation), copy-link functionality, greyed-out summary placeholder.

---

## 6. Technical constraints

- **ADR-001 (Hexagonal Architecture):** No review business rules only in the browser — all validation rules enforced on both client-side (UX feedback) and server-side (data integrity). Specific validations required server-side:
  - Email format (RFC 5322)
  - Full name non-empty
  - SFIA level 1–7 (expert route)
  - Supervisor decision enum (verify | reject)
  - Comment non-empty if provided (both routes)
  - Token validity (must resolve to existing session)
  - Already-submitted check (expert/supervisor cannot save twice)

- **ADR-004 (Voice Engine):** Persistence through FastAPI endpoints defined in Phase 6 revision. Phase 7 defines new admin dashboard endpoints (`GET /api/v1/admin/sessions`, chart aggregates) in the voice engine or documented BFF.

- **Phase 6 `Claim` model + JSONB:** `claims_json` structure defined in Phase 6; do not extend in Phase 7. Phase 7 reads `claims_json` only.

- **Version bump:** Phase 7 adds new API endpoints and response shapes. **Run `/bump-version` to increment MINOR version before implementation begins** (e.g., v0.6.0 → v0.7.0). Create Prisma migration with new version in name if database schema changes (e.g., `prisma migrate dev --name v0_7_0_admin_dashboard_tables`).

---

## 7. Dependencies

| Dependency | Role | Status |
|------------|------|--------|
| Phase 4 ([implemented](../implemented/v0.5/PHASE-4-implementation-assessment-workflow.md)) | `transcript_json` shape (speaker labels, timestamps) for transcript panel | ✅ Ready |
| Phase 5 ([implemented](../implemented/v0.5/PHASE-5-implementation-rag-knowledge-base.md)) | SFIA skill names/descriptions for claims table breakdown rows | ✅ Ready |
| Phase 6 ([TBD](phase-6-claim-extraction-pipeline.md)) | `claims_json` structure, AI-generated summary, dual review tokens (`expert_review_token`, `supervisor_review_token`) | 🔵 In progress |
| Phase 6 Revision ([phase-6-revision-dual-review-tokens.md](phase-6-revision-dual-review-tokens.md)) | Dual-token API routes (`GET/PUT /api/v1/review/expert/{token}`, `GET/PUT /api/v1/review/supervisor/{token}`), extended `IPersistence` port with role-specific save methods | 🔴 **Blocking** — Phase 7 assumes these APIs exist; integration tests will fail if not implemented |
| `frontend/public/admin.html` | Canonical design reference for admin shell (sidebar, stats, charts, table) and review modal layout | ✅ External reference |

**Critical path:** Phase 6 baseline and Phase 6 revision must be completed and deployed before Phase 7 development can proceed to integration testing.

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Phase 6 dual-token APIs not ready on time | Phase 7 blocked; cannot integrate expert/supervisor flows | Lock API schema early; run Phase 6 + Phase 7 in parallel if on same release; Phase 7 integration tests will fail fast if APIs missing |
| Admin sessions API contract unclear | Dashboard implementation stalled | Phase 7 defines the API contract (§1.3); include minimal spec in phase document with filters, pagination, response shape |
| Chart/stats aggregates API missing | Charts show empty state | Phase 7 owns creating these endpoints (calls per day, outcome donut); defined in Phase 6 or Phase 7 depending on dependencies |
| Supervisor rejects without SME context | Review quality suffers | Show expert-adjusted levels read-only on supervisor page; include expert narrative in modal header for context |
| Operator login auth not defined | Dashboard inaccessible during dev | Phase 7 uses simple env-var token auth (`ADMIN_TOKEN`); sufficient for development; Phase 1 auth can replace later |
| PDF export / Approve in mock | UI implies functionality not implemented | Disable or hide buttons until backend APIs exist; document as Phase 8+ feature |
| WCAG compliance | Accessibility debt | Defer WCAG AA to Phase 8; document as known gap; Phase 7 ships without formal audit |

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-01 | `/doc-refiner` refinement pass: Clarified score strip (original + current max levels), sticky footer controls, optional supervisor comments, Phase 7 owns admin API + chart endpoints, explicit build dependencies, comprehensive acceptance criteria with E2E test guidance, validation checklist, version bump requirement, env-var operator auth, full responsive design (≥375px), deferred WCAG AA to Phase 8, risk table with ownership/mitigation |
| 2026-05-01 | Dual-role review: expert vs supervisor URLs, modal-only UI from `frontend/public/admin.html`, final outcome when both complete, Phase 4–6 alignment |
| 2026-05-01 | Operator `/dashboard` must mirror **full** `admin.html` shell (sidebar, stats, charts, table); shared `AssessmentReviewModal`; build order + acceptance criteria |
