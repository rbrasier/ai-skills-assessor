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
- [Assessment Report Contract](../contracts/assessment-report-contract.md): evolve with Phase 7 fields below
- **UI reference (visual + structure):** [`frontend/public/admin.html`](../../../frontend/public/admin.html) — the **assessment detail modal** only (`.modal-overlay` / `.modal` and inner sections). SME and supervisor pages render **that modal pattern full-viewport**; they **must not** expose the admin shell (sidebar, stats, charts, assessment table).
- Phase 4 ([implemented](../implemented/v0.5/PHASE-4-implementation-assessment-workflow.md)): structured `transcript_json` (turns, timestamps, phases) for the transcript panel
- Phase 5 ([implemented](../implemented/v0.5/PHASE-5-implementation-rag-knowledge-base.md)): SFIA skill definitions used when enriching claims (skill names/descriptors in breakdown rows)
- Phase 6: Claim Extraction Pipeline — `claims_json`, transcript column, `review_token` pattern; **extend** with dual tokens and split reviewer payloads (see §0)

**Cross-document note:** PRD-001 §5.2 Data Flow may still show an admin “Trigger Call” arrow; **candidate self-service at `/` is the sole initiation path** per PRD-001 §4.1.

---

## Objective

Build Next.js routes so **two independent reviewers** complete their work through **two unique NanoID URLs**, using the **same modal layout as `frontend/public/admin.html`** (header with candidate facts, score strip, AI summary, SFIA competency breakdown table, transcript section). **Only the controls allowed for that role are editable**; everything else is read-only.

| Reviewer | URL pattern (example) | May edit | Must collect on save |
|----------|----------------------|----------|----------------------|
| **SME (subject matter expert)** | `/review/expert/[token]` | Per claim/skill row: **endorse** the AI-suggested SFIA level **or adjust** to a different level (1–7). Optional short note per row if product requires it; default is level-only. | Full name, work email |
| **Supervisor** | `/review/supervisor/[token]` | Per claim/skill row: **verify** or **reject** the **claims register** entry; **comment** on each row (required for both outcomes). | Full name, work email |

**Final outcome:** The assessment **does not** move to the terminal **final outcome** state until **both** the SME save **and** the supervisor save have succeeded. Order does not matter unless product later defines dependencies.

**Admin dashboard:** Unchanged in scope — authenticated operators use `/dashboard/*` with the full admin chrome. **Experts and supervisors never see that chrome** — only the modal-style review surface.

---

## 0. Prerequisites (Phase 6 extensions)

Phase 6 introduces `claims_json`, transcript storage, and a single `review_token`. Phase 7 requires:

### 0.1 Two opaque tokens

Store **two unique** NanoIDs on `assessment_sessions` (names illustrative):

| Column | Purpose |
|--------|---------|
| `expert_review_token` | URL for SME/expert modal |
| `supervisor_review_token` | URL for supervisor modal |

Same entropy and expiry policy as the existing review token (e.g. 30 days configurable). **Either token invalid/expired → 404** with generic message.

### 0.2 Claim / report payload shape (conceptual)

Extend persisted claim objects (and API responses) so each claim row can carry:

**Expert fields (written only via expert token):**

- `expert_level`: integer 1–7 — endorsed or adjusted level (required before expert submission)
- `expert_submitted_at`, `expert_full_name`, `expert_email` — captured when expert clicks **Save**

**Supervisor fields (written only via supervisor token):**

- `supervisor_decision`: `verified` \| `rejected` per claim
- `supervisor_comment`: string (**required** for every row — verify and reject)
- `supervisor_submitted_at`, `supervisor_full_name`, `supervisor_email` — captured when supervisor clicks **Save**

**Aggregated report status** (session-level), e.g. extend `report_status`:

- After Phase 6 pipeline: `generated` / `sent` / … as today
- During reviews: e.g. `awaiting_expert`, `awaiting_supervisor`, `reviews_complete` — exact enum TBD in implementation but **must** include a state meaning “both reviewers have submitted” before HR/export outcomes run

Idempotency: saving again with the same token after success returns **409** or a clear “already submitted” payload.

### 0.3 API surface (voice engine or BFF)

Illustrative paths (prefix `/api/v1`):

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/review/expert/{token}` | Load report + transcript + claims for SME surface |
| `PUT` | `/review/expert/{token}` | Expert save: body includes `reviewer_full_name`, `reviewer_email`, and per-claim `expert_level` (and optional notes) |
| `GET` | `/review/supervisor/{token}` | Load same read-only context + show expert-adjusted levels as read-only |
| `PUT` | `/review/supervisor/{token}` | Supervisor save: body includes `reviewer_full_name`, `reviewer_email`, per-claim `supervisor_decision`, `supervisor_comment` |

**Rule:** Implement persistence + validation server-side (honest capability separation — expert token cannot set supervisor fields and vice versa). Phase 7 frontend work is blocked until these endpoints exist.

---

## 1. Deliverables

### 1.1 Application layout

**Tech stack:** Next.js 14+ App Router, Tailwind (map CSS variables from `admin.html` modal tokens: `--paper`, `--ink`, `--accent`, `--line`, fonts Inter Tight / Instrument Serif / JetBrains Mono), Lucide icons optional.

**Route structure:**

```
packages/web/src/app/
├── layout.tsx
├── page.tsx                                    ← Candidate portal (Phase 2) — unchanged
├── (dashboard)/                                ← Full admin UI — operators only
│   └── ...                                     ← §1.4 admin (existing plan)
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

**Layout rule:** Pages under `/review/expert/*` and `/review/supervisor/*` render **only** the modal container (equivalent to `#modalOverlay` + `#modal` content). **Do not** mount `.shell`, `.sidebar`, `.main` page chrome from `admin.html`.

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

All header actions in the static mock (**Export PDF**, **Approve**) are **hidden or read-only** on expert/supervisor routes unless a separate product decision adds them later.

### 1.3 Component split (suggested)

```
packages/web/src/components/
├── review-modal/
│   ├── ReviewModalShell.tsx           ← Overlay + card — matches .modal-overlay / .modal
│   ├── ModalHeader.tsx                ← Read-only facts
│   ├── ScoreStrip.tsx
│   ├── AiSummaryPanel.tsx
│   ├── ClaimsRegisterTable.tsx        ← Skill rows; receives slot for role-specific right column
│   ├── TranscriptPanel.tsx
│   ├── ExpertClaimControls.tsx        ← Level endorse/adjust only
│   ├── SupervisorClaimControls.tsx    ← Verify/reject + comment
│   └── ReviewerIdentityForm.tsx       ← Name + email — modal step before PUT
├── dashboard/                         ← Unchanged from operator dashboard plan
└── ui/
```

Reuse Tailwind tokens derived from `admin.html` `:root` variables for visual parity.

### 1.4 Admin dashboard (operators)

Scope unchanged: `/dashboard/*` full layout with table, filters, links to copy **both** review URLs when tokens exist. No expert/supervisor chrome here.

### 1.5 Security

- **Knowledge-based URLs:** Two independent NanoIDs; supervisor cannot guess expert URL without the link.
- **Capability isolation:** Server rejects cross-role field writes.
- **HTTPS**, rate limiting, no candidate PII in paths.
- **Reviewer PII:** Name and email stored on submission for audit trail (GDPR/retention policy out of scope for this doc).

---

## 2. UI/UX requirements

- **Visual fidelity:** Match modal typography, spacing, card radius, and ladder/confidence patterns from `frontend/public/admin.html`.
- **Responsive:** Modal scrolls inside viewport; usable from **768px** width (tablet).
- **Accessibility:** WCAG AA; ladder + decisions not colour-only; labelled controls for expert/supervisor edits.
- **States:** Loading; 404/expired token; network error with retry; **already submitted** (read-only view of saved decisions + reviewer identity timestamp if API returns it).

---

## 3. Build order (within Phase 7)

1. Extract shared modal styles/tokens from `frontend/public/admin.html` into the Next app (Tailwind theme or CSS module).
2. Implement read-only `ClaimsRegisterTable` + `TranscriptPanel` from API fixture matching Phase 6 shape.
3. Expert route: level controls + identity capture + `PUT` expert.
4. Supervisor route: verify/reject + comments + identity + `PUT` supervisor.
5. Wire dashboard to display dual links and session `report_status` including “awaiting expert”, “awaiting supervisor”, “reviews complete”.
6. Accessibility and error-state pass.

---

## 4. Definition of Done

- Expert and supervisor pages show **only** the modal surface (no admin shell).
- Both flows persist reviewer name/email and role-specific decisions server-side.
- Final outcome progression occurs **only** after both saves succeed (verified via API + UI).
- Types align with updated contract / OpenAPI once Phase 6 extensions land.

---

## 5. Acceptance criteria

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
- [ ] Dashboard lists/links **both** URLs for operators when tokens exist.
- [ ] Keyboard navigation and labels meet WCAG AA on editable controls.

---

## 6. Technical constraints

- **ADR-001:** No review business rules only in the browser — validation duplicated server-side.
- **ADR-004:** Persistence via voice engine (or documented BFF) through existing ports.
- **Phase 6 `Claim` model:** Extend in code + migration when adding expert/supervisor columns / JSON fields — coordinate MINOR version bump per repo versioning rules when schema changes.

---

## 7. Dependencies

| Dependency | Role |
|------------|------|
| Phase 4 | `transcript_json` shape for transcript panel |
| Phase 5 | Skill names/descriptions for breakdown rows |
| Phase 6 | `claims_json`, pipeline-generated summary, dual tokens + extended persistence |
| `frontend/public/admin.html` | Canonical modal layout reference |

---

## 8. Risks

| Risk | Mitigation |
|------|------------|
| Schema drift vs Phase 6 | Lock API schema before UI integration; contract tests |
| Supervisor rejects without SME context | Show expert-adjusted levels read-only on supervisor page |
| Legal / privacy for reviewer emails | Align retention with HR policy |
| PDF export expectation from mock | Explicitly out of scope on token URLs unless added later |

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-01 | Refine pass: `/dashboard` vs `/`, Phase 6 API notes |
| 2026-05-01 | Dual-role review: expert vs supervisor URLs, modal-only UI from `frontend/public/admin.html`, final outcome when both complete, Phase 4–6 alignment |
