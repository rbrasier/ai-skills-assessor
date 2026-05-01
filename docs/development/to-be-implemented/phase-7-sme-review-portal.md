# Phase 7: SME Review Portal (Next.js Frontend)

## Status
To Be Implemented

## Date
2026-05-01

## References
- PRD-001: Voice-AI Skills Assessment Platform (candidate self-service intake; read-only admin monitoring)
- PRD-002: Assessment Interview Workflow (post-call report shape, SME review expectations)
- ADR-001: Hexagonal Architecture (UI calls APIs/adapters — no business rules duplicated in the frontend)
- ADR-004: Voice Engine Technology (FastAPI voice engine owns persistence for sessions and reports in current plan)
- [Assessment Report Contract](../contracts/assessment-report-contract.md): shared `AssessmentReport` / `ExtractedClaim` shapes
- Phase 1: Foundation & Monorepo Scaffold (Next.js shell)
- Phase 6: Claim Extraction Pipeline (produces `claims_json`, `review_token`, `GET /api/v1/review/{token}`)

**Cross-document note:** PRD-001 §5.2 Data Flow diagram still shows an admin “Trigger Call” arrow; **candidate self-service at `/` is the sole initiation path** per PRD-001 §4.1. This phase document supersedes that diagram for implementation order.

## Objective

Build the Next.js frontend (`packages/web`) with two primary interfaces: a read-only Admin Dashboard for monitoring assessment status and history, and an SME Review Portal where subject matter experts can review, approve, adjust, or reject AI-extracted claims. The SME route is accessed via unique NanoID-based URLs (`/review/[token]`).

**Note:** Assessment calls are candidate-initiated via the self-service portal at **`/`** (candidate intake from Phase 2). The admin dashboard is monitoring-only — it does not trigger calls or outbound dial.

---

## 0. Prerequisites (Phase 6 API surface)

Phase 6 defines **`GET /api/v1/review/{review_token}`** returning report payload or **404** when the token is missing or expired. Phase 7 UI assumes **additional voice-engine endpoints** for persisting SME decisions (not yet listed in the Phase 6 excerpt):

| Method | Path | Purpose |
|--------|------|---------|
| `PATCH` | `/api/v1/review/{review_token}/claims/{claim_id}` | Persist per-claim decision: `approved` \| `adjusted` \| `rejected`; optional `adjusted_level` (1–7), `notes` |
| `POST` | `/api/v1/review/{review_token}/submit` | Finalise review: set `report_status` to completed, set `sme_reviewed_at`, reject further edits |

**Rule:** Implement or extend these on the voice engine (or a dedicated BFF that writes through the same persistence port) **before** marking Phase 7 complete; the acceptance criteria below reference this contract.

---

## 1. Deliverables

### 1.1 Application Layout & Navigation

**Tech Stack:**
- Next.js 14+ with App Router
- Tailwind CSS for styling
- Lucide-React for icons
- Server Components by default, Client Components where interactivity is needed

**Route structure (path collision avoided):** The candidate portal **must remain at `/`**. Admin routes live under the **`/dashboard`** prefix so `/` is not overwritten.

```
packages/web/src/app/
├── layout.tsx                          ← Root layout (Tailwind, fonts, metadata)
├── page.tsx                            ← Candidate self-service portal (Phase 2: intake + call status)
├── (dashboard)/                        ← Route group; URLs below omit the group name
│   ├── layout.tsx                      ← Dashboard layout (sidebar, header)
│   ├── dashboard/
│   │   ├── page.tsx                    ← GET /dashboard — recent assessments (read-only)
│   │   ├── assessments/
│   │   │   ├── page.tsx                ← GET /dashboard/assessments — list
│   │   │   └── [id]/
│   │   │       └── page.tsx            ← GET /dashboard/assessments/[id] — detail
│   │   └── candidates/
│   │       ├── page.tsx                ← GET /dashboard/candidates
│   │       └── [id]/
│   │           └── page.tsx            ← GET /dashboard/candidates/[id]
│   └── api/                            ← Next.js Route Handlers (server-only secrets)
│       └── admin/
│           └── sessions/
│               └── route.ts            ← GET: proxy to voice engine admin list API
├── (review)/
│   └── review/
│       └── [token]/
│           ├── layout.tsx              ← Minimal review layout (no sidebar)
│           └── page.tsx                ← GET /review/[token] — SME review UI
└── api/                                ← Optional: other public proxies if needed
    └── assessment/
        └── status/
            └── route.ts                ← GET: status proxy for candidate page (if not folded into Phase 2)
```

**Note:** There is no `/assessments/new` route and no admin “new assessment” flow. Candidates start assessments only from `/`.

**Session status vocabulary (UI):** Use the same labels as the backend where possible. **`processed`** means post-call extraction finished and a report exists; **`completed`** may mean call ended without processing — align column badges with API `status` and `report_status` fields to avoid confusion (e.g. show “Report ready” when `report_status` is `generated` or later).

### 1.2 Admin Dashboard (Read-Only Monitoring)

The admin dashboard provides read-only visibility into all assessment sessions. It does **not** trigger calls — assessment initiation is candidate self-service via the portal at `/` (Phase 2).

**Routes (all under `/dashboard`):**
- `/dashboard` → Recent sessions overview (read-only)
- `/dashboard/assessments` → Paginated session list with filters
- `/dashboard/assessments/[id]` → Session detail (transcript, recording, extracted claims when present)
- `/dashboard/candidates` → Candidate list (keyed by WORK EMAIL)
- `/dashboard/candidates/[id]` → Candidate profile + assessment history

**Data source:** Dashboard server components or Route Handlers call the voice engine **`GET /api/v1/admin/sessions`** (or equivalent agreed in Phase 1/6) with optional filters:
- Status: `pending`, `dialling`, `in_progress`, `completed`, `processed`, `failed`, `cancelled`
- Email: search by candidate WORK EMAIL
- Date range: `since` / `until`

#### Assessment List

**Route:** `/dashboard/assessments`

Displays a table of all assessments with:
- Candidate work email
- Phone number (masked: show country code + last 3–4 digits only, e.g. `+61 •••••7890`)
- Status badge aligned with API: `pending`, `dialling`, `in_progress`, `completed`, `processed`, `failed`, `cancelled`
- Started date/time (timezone: display in browser locale or fixed `Australia/Sydney` — pick one and document in UI copy)
- Actions: **View detail** only (read-only). Optional **Copy review link** when `review_url` or `review_token` is present — never “trigger processing” from the dashboard.

#### Assessment Detail

**Route:** `/dashboard/assessments/[id]`

Shows:
- Assessment status timeline
- Full transcript (if available)
- Call recording player (if available)
- Extracted claims (if processed)
- Link to SME review portal

### 1.3 SME Review Portal

**Route:** `/review/[token]`

This is the critical deliverable — the interface SMEs use to review AI-extracted claims.

#### Design Principles
- **Minimal chrome**: No sidebar, no navigation. Focus entirely on the review task.
- **One claim at a time**: Option to review claims sequentially or see the full list.
- **Clear context**: Each claim shows the verbatim quote, AI interpretation, and SFIA mapping.
- **Action-oriented**: Approve, adjust, or reject with minimal clicks.

#### Review Page Layout

```
┌──────────────────────────────────────────────────────┐
│  SFIA Skills Assessment Review                       │
│  Candidate: Jane Smith | Date: 16 Apr 2026           │
│  Assessment ID: abc-123-def                          │
├──────────────────────────────────────────────────────┤
│                                                      │
│  Progress: ████████░░░░ 5 of 12 claims reviewed      │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  Claim #6                                      │  │
│  │                                                │  │
│  │  VERBATIM QUOTE                                │  │
│  │  "I managed a cross-functional team of 12      │  │
│  │   developers and 3 QA engineers across the     │  │
│  │   Sydney and Melbourne offices for the          │  │
│  │   platform migration project"                  │  │
│  │                                                │  │
│  │  AI INTERPRETATION                             │  │
│  │  Managed a team of 15 across two locations     │  │
│  │  for a platform migration project              │  │
│  │                                                │  │
│  │  AI MAPPING                                    │  │
│  │  Skill: ITMG (IT Management) ──── Level: 5     │  │
│  │  Confidence: ████████░░ 82%                    │  │
│  │                                                │  │
│  │  AI REASONING                                  │  │
│  │  "Cross-functional team leadership across      │  │
│  │   multiple locations indicates Level 5          │  │
│  │   influence and autonomy..."                   │  │
│  │                                                │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐      │  │
│  │  │ ✓ Approve│ │ ✎ Adjust │ │ ✗ Reject │      │  │
│  │  └──────────┘ └──────────┘ └──────────┘      │  │
│  │                                                │  │
│  │  [If Adjust selected:]                         │  │
│  │  Adjusted Level: [dropdown 1-7]                │  │
│  │  Notes: [textarea]                             │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ◀ Previous Claim    Claim 6 of 12    Next Claim ▶  │
│                                                      │
├──────────────────────────────────────────────────────┤
│  Skill Summary (live-updating)                       │
│  ┌────────────┬───────┬────────────┬───────────┐    │
│  │ Skill      │ Level │ Claims     │ Status    │    │
│  ├────────────┼───────┼────────────┼───────────┤    │
│  │ ITMG       │ 5     │ 3 claims   │ 2/3 done  │    │
│  │ PROG       │ 4     │ 4 claims   │ 1/4 done  │    │
│  │ TEST       │ 3     │ 2 claims   │ 0/2 done  │    │
│  │ ARCH       │ 5     │ 3 claims   │ 2/3 done  │    │
│  └────────────┴───────┴────────────┴───────────┘    │
│                                                      │
│  [Submit Final Assessment] (enabled when all done)   │
└──────────────────────────────────────────────────────┘
```

#### Key Components

```
packages/web/src/components/
├── review/
│   ├── ReviewPage.tsx              ← Main review page (server component)
│   ├── ClaimReviewCard.tsx         ← Individual claim review widget
│   ├── ClaimNavigator.tsx          ← Previous/Next navigation
│   ├── SkillSummaryTable.tsx       ← Aggregated skill overview
│   ├── ConfidenceBadge.tsx         ← Visual confidence indicator
│   ├── LevelAdjuster.tsx           ← Level dropdown for adjustments
│   └── SubmitReviewButton.tsx      ← Final submission
├── dashboard/
│   ├── AssessmentTable.tsx         ← Assessment list table
│   ├── StatusBadge.tsx             ← Status pill component
│   └── TranscriptViewer.tsx        ← Transcript display
└── ui/
    ├── Button.tsx
    ├── Card.tsx
    ├── Input.tsx
    ├── Badge.tsx
    ├── Table.tsx
    ├── Progress.tsx
    └── Dialog.tsx
```

### 1.4 API Integration

- **Admin session list/detail:** Prefer **server-side** `fetch` from Server Components or Route Handlers (`packages/web/src/app/(dashboard)/api/...`) so voice-engine base URL and any future admin secrets stay **server-only** (`VOICE_ENGINE_URL`, not `NEXT_PUBLIC_*`).
- **SME review (`/review/[token]`):** Loading report data can use the public **`NEXT_PUBLIC_VOICE_ENGINE_URL`** only if the voice engine is intentionally public on that host; otherwise proxy **`GET /api/v1/review/{token}`** through a Next Route Handler as well. Mutations (`PATCH` claim, `POST` submit) **must not rely on hidden secrets** — token-in-URL is the credential — but using same-origin Route Handlers avoids CORS and centralises logging.

#### Review API Calls (example client module)

Use JSON keys that match the FastAPI/Pydantic models (e.g. `adjusted_level` snake_case) unless the API is standardised on camelCase — align with generated types from the Assessment Report Contract.

```typescript
// packages/web/src/lib/review-api.ts

const base =
  typeof window === "undefined"
    ? process.env.VOICE_ENGINE_URL ?? "http://localhost:8000"
    : process.env.NEXT_PUBLIC_VOICE_ENGINE_URL ?? "http://localhost:8000";

export async function getReviewByToken(token: string) {
  const res = await fetch(`${base}/api/v1/review/${token}`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Review load failed: ${res.status}`);
  return res.json();
}

export async function submitClaimReview(
  token: string,
  claimId: string,
  body: {
    status: "approved" | "adjusted" | "rejected";
    adjusted_level?: number;
    notes?: string;
  }
) {
  const res = await fetch(`${base}/api/v1/review/${token}/claims/${claimId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 409) throw new Error("Review already finalised");
  if (!res.ok) throw new Error(`Claim update failed: ${res.status}`);
  return res.json();
}

export async function submitFinalReview(token: string) {
  const res = await fetch(`${base}/api/v1/review/${token}/submit`, { method: "POST" });
  if (res.status === 409) throw new Error("Already submitted");
  if (!res.ok) throw new Error(`Final submit failed: ${res.status}`);
  return res.json();
}
```

### 1.5 Security Considerations

- **No authentication on review links**: Access is via the NanoID token (knowledge-based security). This is intentional for simplicity — SMEs should not need an account.
- **Token expiry**: Review links expire after 30 days (configurable). Expired tokens return 404.
- **Rate limiting**: Review endpoints are rate-limited to prevent brute-force token guessing. NanoID with 21 characters from a 62-char alphabet provides ~130 bits of entropy.
- **No PII in URL**: The token is opaque; no candidate info is in the URL.
- **HTTPS only**: Review portal is served over TLS.

---

## 2. UI/UX Requirements

### Design System
- **Colour palette**: Indigo primary, gray neutrals, green/amber/red for status.
- **Typography**: Inter or system font stack.
- **Spacing**: 4px base unit (Tailwind default).
- **Border radius**: Rounded-md (6px) for cards and inputs.
- **Shadows**: Subtle shadows for card elevation.

### Responsive Design
- Dashboard: Desktop-first (table-heavy).
- Review portal: Must work on tablet (SMEs may review on iPad).
- Minimum supported width: 768px.

### Accessibility
- All interactive elements are keyboard-navigable.
- Colour is not the sole indicator of status (icons + labels + colour).
- Sufficient colour contrast (WCAG AA).
- Form inputs have associated labels.

---

## 3. Build Order (within Phase 7)

1. **Route scaffolding:** `/dashboard/*` layout + placeholder pages without breaking `/` from Phase 2.
2. **Admin list:** Table + filters + pagination against `GET /api/v1/admin/sessions` (or proxied equivalent).
3. **Admin detail:** Transcript viewer + recording player + read-only claims when `claims_json` present.
4. **Review page:** Load report by token; 404/expired states; claim card + navigation.
5. **Review mutations:** Wire `PATCH` per claim and `POST` submit; handle idempotency/`409` when already finalised.
6. **Polish:** Skill summary aggregation, accessibility pass, tablet breakpoints.

---

## 4. Definition of Done

- All **§5 Acceptance Criteria** are checked off in a test environment against a running voice engine with seed data.
- No admin UI path triggers outbound calls or re-runs extraction without an explicitly documented operator-only flow (none in v1).
- Types for API responses align with [Assessment Report Contract](../contracts/assessment-report-contract.md) (or generated TS types from it).
- Error states are implemented for: empty assessment list, session with no transcript yet, session with failed extraction, invalid/expired review token, network failure on submit (user-visible message + retry).

---

## 5. Acceptance Criteria

- [ ] Dashboard: `/dashboard/assessments` shows a **paginated** list (default **25** rows per page, configurable in code) with **no** call-trigger or processing-trigger controls.
- [ ] Dashboard: `/dashboard/assessments` supports filtering by **status**, **candidate email** (substring match), and **date range** (`since` / `until` ISO dates) as passed to the admin API.
- [ ] Dashboard: `/dashboard/assessments/[id]` shows session detail; **transcript** when present; **recording** player when `recording_url` present; **extracted claims** when report exists; link or button to open **`/review/[token]`** when review token exists.
- [ ] Review: `/review/[token]` loads the report returned by `GET /api/v1/review/{token}` for a valid, unexpired token.
- [ ] Review: `/review/[token]` shows a dedicated **not found / expired** UI when the API returns **404** (do not leak whether a token ever existed).
- [ ] Review: Each claim shows **verbatim quote**, **interpretation**, **SFIA skill code/name**, **level**, **confidence**, and **reasoning** per contract fields.
- [ ] Review: SME can **approve** a claim with one explicit action (e.g. button) without mandatory notes.
- [ ] Review: SME can **adjust** a claim: change level (**1–7**), optional notes; cannot submit adjust without a selected level.
- [ ] Review: SME can **reject** a claim with optional notes.
- [ ] Review: Progress indicator reflects **count of claims with a terminal SME decision** / total claims.
- [ ] Review: Skill summary reflects current decisions **after each successful PATCH** (optimistic update allowed if rolled back on failure).
- [ ] Review: "Submit Final Assessment" is **disabled** until every claim has a terminal decision; **enabled** when all are decided.
- [ ] Review: Successful final submission returns **2xx** and UI shows confirmation; subsequent submit shows **clear already-submitted state** (e.g. `409` handling).
- [ ] Responsive: Review portal layout is usable at **768px** width and above (tablet).
- [ ] Accessibility: Visible labels, focus order, and keyboard operation for approve/adjust/reject and navigation.

## 6. Technical Constraints

- **ADR-001:** Frontend contains presentation and API orchestration only; persistence rules remain in core/voice-engine services.
- **ADR-004:** Review and admin APIs are served by the **voice engine (FastAPI)** unless a later ADR introduces a separate BFF; Next Route Handlers may proxy only.
- **Contract:** Claim `id` values are UUIDs matching Phase 6 `claims_json` — use them in `PATCH` paths.
- **CORS / auth:** SME links are **unauthenticated**; rate limiting is server-side (see §1.5).

## 7. Dependencies

| Dependency | Role | Status |
|------------|------|--------|
| Phase 1 | Next.js shell, routing, shared types | 🔵 Planned / in progress (per repo state) |
| Phase 2 | Candidate **`/`** intake + call status (must not regress) | 🔵 Planned / in progress |
| Phase 6 | `claims_json`, `review_token`, `GET /api/v1/review/{token}`, persistence | 🔵 To Be Implemented |
| Phase 6 extension | `PATCH` claim + `POST` submit final (see §0) | 🔵 Required before Phase 7 complete |
| Voice engine | Running API for admin + review routes | External |

If Phase 6 ships without the PATCH/POST endpoints, Phase 7 stops at **read-only** review UI until those endpoints exist.

## 8. Risks

| Risk | Mitigation |
|------|------------|
| SME experience confusing | User testing with real SFIA practitioners; iterate on layout |
| Review link sharing (unintended access) | NanoID entropy is sufficient; add optional PIN in v2 |
| Large number of claims per assessment | Sequential review mode + optional list view; summary collapses long lists |
| Network errors during review submission | Retry with exponential backoff; show persistent error banner; optional localStorage draft for in-progress notes (not for security tokens) |
| Phase 6 / API mismatch | Lock request/response shapes to Assessment Report Contract + explicit FastAPI models; add contract tests or OpenAPI snapshot |

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-01 | Refine pass: fixed `/` vs dashboard route clash (`/dashboard/*`), removed trigger-processing contradiction, aligned paths with `packages/web`, added Phase 6 PATCH/POST prerequisite, ADR/contract refs, build order, Definition of Done, testable acceptance criteria |
