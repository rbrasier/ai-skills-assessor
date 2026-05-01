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
| Score strip (`.score-strip` / `.score-cell`) | Derived: max SFIA level from claims, avg confidence, skill count, duration, provisional outcome label |
| `.summary-box` — AI-generated summary | Phase 6 narrative / exec summary field on report (if absent, hide kicker or show placeholder until API provides) |
| `.skills-table` — `.skill-detail-row` | **One row per claim** in `claims_json`: skill name/code, descriptor (from Phase 5 definition or claim text), evidence quote + transcript time ref, level ladder, confidence bar |
| `.transcript-section` | `transcript_json` from Phase 4 — speaker labels, timestamps, optional evidence tags |

**Role-specific controls (bottom of modal body or footer — not in mock):**

- **Expert:** Per row: level control (endorse AI level vs select adjusted 1–7). Primary **Save** opens or precedes a step collecting **full name** + **email** (validate email format), then submits.
- **Supervisor:** Per row: **Verify** or **Reject** + **comment** (required). **Save** collects **full name** + **email**, then submits.

All header actions in the static mock (**Export PDF**, **Approve**) are **hidden or disabled** on expert/supervisor routes unless product adds operator-only workflow later. On **dashboard** modal open, **Approve** / **Export PDF** remain **non-functional placeholders** until a later phase defines APIs — or hide them for parity without implying behaviour.

### 1.3 Admin shell parity (`frontend/public/admin.html`)

Port the **non-modal** chrome so `/dashboard` matches the mock:

| Mock region | Behaviour |
|-------------|-----------|
| `.shell` | CSS grid: sidebar (220px) + main |
| `.sidebar` | Brand, nav groups (Analytics: Dashboard, Candidates; Configuration: Skills library, Settings — labels may stay placeholder until those routes exist), user chip (from auth/session or config) |
| `.main` `.topbar` | Title (“Assessment Overview”), **Candidate portal** primary button → `/` |
| `.page` `.page-head` | Title + subtitle (derive counts from API: completed calls, awaiting review, last call) |
| `#statsRow` `.stats` | Stat cards — wire real aggregates where API exists; **Awaiting review** card shows report-count metrics when available |
| `.charts` | Bar chart (calls per day) + donut (call outcomes) — use **real session/report data** when endpoint supports it; otherwise stub with empty state **only if** documented |
| `.table-card` | Toolbar (filters: All / Complete / Awaiting review / Incomplete), search (name, email, skill), header row, body rows matching `.trow` grid columns |
| Row click | Opens shared **`AssessmentReviewModal`** (same component as token flows) in **`variant="operator-read-only"`** — hide expert/supervisor edit footers; show `report_status` + **copy** actions for expert/supervisor URLs when tokens exist |

**Data:** Prefer `GET /api/v1/admin/sessions` (or equivalent from Phase 1/6) with filters aligned to mock tabs. Pagination: match PRD/Phase 6 admin API when specified; otherwise client-side slice with a TODO for server pagination.

### 1.4 Shared modal component

Use one **`AssessmentReviewModal`** (contents per §1.2) with props: `variant: "expert" | "supervisor" | "operator-read-only"`.

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
- **Responsive:** Token review modals usable from **768px**+ (tablet). **Dashboard:** **desktop-first** (≥1280px target, matching mock viewport); narrow screens may horizontal-scroll or collapse sidebars only if explicitly designed — default is operator desktop use.
- **Accessibility:** WCAG AA on dashboard table, filters, modals, and token flows.
- **States:** Loading; empty table; 404/expired token; network error with retry; **already submitted** on token routes (read-only view when API returns completed state).

---

## 3. Build order (within Phase 7)

1. Extract shared design tokens from `frontend/public/admin.html` into the Next app (Tailwind theme or CSS module).
2. **Admin shell:** Layout, sidebar, topbar, stats row, charts, assessments table — wired to admin sessions API (or fixture → API).
3. **Shared `AssessmentReviewModal`:** Read-only core (header, score strip, summary, claims table, transcript); open from table row with `variant="operator-read-only"`.
4. Expert token route: mount modal only + `variant="expert"` + `PUT` expert flow.
5. Supervisor token route: `variant="supervisor"` + `PUT` supervisor flow.
6. Dashboard modal: copy-link UI for both URLs; reflect `report_status` in table badges/chips.
7. Accessibility pass (dashboard + modals + token pages).

---

## 4. Definition of Done

- **`/dashboard`:** Visual and structural parity with **`frontend/public/admin.html`** shell (sidebar, stats, charts, assessments table, topbar link to `/`). Data from real admin API where available.
- Expert and supervisor token pages show **only** the modal surface (no admin shell).
- **`AssessmentReviewModal`** reused for operators (read-only) and both token roles.
- Both expert/supervisor flows persist reviewer name/email and role-specific decisions server-side.
- Final outcome progression occurs **only** after both saves succeed (verified via API + UI).
- Types align with updated contract / OpenAPI once Phase 6 revision lands.

---

## 5. Acceptance criteria

- [ ] **`GET /dashboard`** (or agreed path under `/dashboard`) renders the **full** admin shell matching `admin.html`: `.shell` grid, sidebar brand + nav groups, topbar with **Candidate portal** → `/`, page title/subtitle, stats row, charts row, assessments table with toolbar filters + search.
- [ ] Table rows match mock column intent (candidate, email, date, duration, top skills, max level, confidence); data from **`GET /api/v1/admin/sessions`** (or equivalent).
- [ ] Row click opens **`AssessmentReviewModal`** in operator read-only mode with the same inner content as token flows (header, scores, summary, claims breakdown, transcript).
- [ ] Operator modal shows **copy** actions (or equivalent) for **expert** and **supervisor** review URLs when tokens exist; shows review progress / `report_status` when API provides it.
- [ ] `/review/expert/[token]` renders the assessment modal layout consistent with `frontend/public/admin.html` (modal only — **no** sidebar, stats, charts, or main table).
- [ ] `/review/supervisor/[token]` meets the same visual/structural requirement.
- [ ] Expert page: all modal content except expert level controls is **read-only**; expert can **endorse** (accept AI level) or **adjust** SFIA level **1–7** per claim row.
- [ ] Expert **Save** requires **full name** and **valid email** before `PUT` succeeds.
- [ ] Supervisor page: all modal content except supervisor verify/reject + comment is **read-only**.
- [ ] Supervisor **Save** requires **full name** and **valid email**; **every** row has a **non-empty comment** (required for both verify and reject).
- [ ] Invalid/expired tokens show generic **not found** (no existence leak).
- [ ] After expert has saved, supervisor view shows expert-adjusted levels as **read-only**.
- [ ] `report_status` (or equivalent) advances to **final-outcome-eligible** only when **both** expert and supervisor submissions exist.
- [ ] Second submit with same role returns handled **already completed** state (`409` or equivalent UX).
- [ ] Keyboard navigation and labels meet WCAG AA on dashboard and token flows.

---

## 6. Technical constraints

- **ADR-001:** No review business rules only in the browser — validation duplicated server-side.
- **ADR-004:** Persistence via voice engine (or documented BFF) through existing ports.
- **Phase 6 `Claim` model + JSONB:** Defined in Phase 6 §1.1 and persisted in `claims_json`; MINOR version bump when extending schema (Phase 6 prerequisites).

---

## 7. Dependencies

| Dependency | Role |
|------------|------|
| Phase 4 | `transcript_json` shape for transcript panel |
| Phase 5 | Skill names/descriptions for breakdown rows |
| Phase 6 | `claims_json`, pipeline-generated summary, dual tokens + extended persistence |
| `frontend/public/admin.html` | Canonical reference for **full operator page** + **modal** |

---

## 8. Risks

| Risk | Mitigation |
|------|------------|
| Schema drift vs Phase 6 | Lock API schema before UI integration; contract tests |
| Charts/stats need aggregates API | Time-series + outcome buckets may require dashboard-specific endpoints or Phase 6 revision — define minimal API or documented stubs |
| Supervisor rejects without SME context | Show expert-adjusted levels read-only on supervisor page |
| Legal / privacy for reviewer emails | Align retention with HR policy |
| PDF export / Approve in mock | Placeholder or hidden until backend exists; avoid implying behaviour |

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-01 | Refine pass: `/dashboard` vs `/`, Phase 6 API notes |
| 2026-05-01 | Dual-role review: expert vs supervisor URLs, modal-only UI from `frontend/public/admin.html`, final outcome when both complete, Phase 4–6 alignment |
| 2026-05-01 | Operator `/dashboard` must mirror **full** `admin.html` shell (sidebar, stats, charts, table); shared `AssessmentReviewModal`; build order + acceptance criteria updated |
