# Phase 7: SME Review Portal (Next.js Frontend)

## Status
To Be Implemented

## Date
2026-04-18

## References
- PRD-001: Voice-AI Skills Assessment Platform
- Phase 1: Foundation & Monorepo Scaffold (Next.js shell)
- Phase 6: Claim Extraction Pipeline (produces reports)

## Objective

Build the Next.js frontend with two primary interfaces: a read-only Admin Dashboard for monitoring assessment status and history, and an SME Review Portal where subject matter experts can review, approve, adjust, or reject AI-extracted claims. The portal is accessed via unique NanoID-based URLs.

**Note:** Assessment calls are candidate-initiated via the self-service portal (`/`, Phase 2). The admin dashboard is monitoring-only — it does not trigger calls.

---

## 1. Deliverables

### 1.1 Application Layout & Navigation

**Tech Stack:**
- Next.js 14+ with App Router
- Tailwind CSS for styling
- Lucide-React for icons
- Server Components by default, Client Components where interactivity is needed

**Route Structure:**

```
apps/web/src/app/
├── layout.tsx                          ← Root layout (Tailwind, fonts, metadata)
├── page.tsx                            ← Candidate self-service portal (Phase 2: intake form + call status)
├── (dashboard)/
│   ├── layout.tsx                      ← Dashboard layout (sidebar, header)
│   ├── page.tsx                        ← Dashboard home (recent assessments — read-only)
│   ├── assessments/
│   │   ├── page.tsx                    ← Assessment list (read-only)
│   │   └── [id]/
│   │       └── page.tsx               ← Assessment detail (status, transcript, recording)
│   └── candidates/
│       ├── page.tsx                    ← Candidate list
│       └── [id]/
│           └── page.tsx               ← Candidate profile + assessment history
├── (review)/
│   └── [token]/
│       ├── layout.tsx                  ← Minimal review layout (no sidebar)
│       └── page.tsx                    ← SME review interface
└── api/
    └── assessment/
        └── status/
            └── route.ts               ← GET: status proxy to voice engine
```

**Note:** There is no `/assessments/new` route. Calls are triggered by candidates via the self-service portal (`/`). The admin dashboard has no trigger capability.

### 1.2 Admin Dashboard (Read-Only Monitoring)

The admin dashboard provides read-only visibility into all assessment sessions. It does **not** trigger calls — assessment initiation is candidate self-service via the portal at `/` (Phase 2).

**Routes:**
- `/` (dashboard home) → Recent sessions overview
- `/assessments` → Paginated session list with filters
- `/assessments/[id]` → Session detail (transcript, recording, extracted claims)
- `/candidates` → Candidate list (keyed by WORK EMAIL)
- `/candidates/[id]` → Candidate profile + assessment history

**Data source:** Admin dashboard calls `GET /api/v1/admin/sessions` with optional filters:
- Status: `pending`, `dialling`, `in_progress`, `completed`, `failed`, `cancelled`
- Email: search by candidate WORK EMAIL
- Date range: `since` / `until`

#### Assessment List

**Route:** `/assessments`

Displays a table of all assessments with:
- Candidate work email
- Phone number (masked: +XX*****XXX)
- Status badge (pending, dialling, in_progress, completed, processed, failed, cancelled)
- Started date/time
- Actions (view detail, trigger processing)

#### Assessment Detail

**Route:** `/assessments/[id]`

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
apps/web/src/components/
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
│   ├── TriggerAssessmentForm.tsx   ← New assessment form
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

#### Review API Calls (Client-Side)

```typescript
// lib/api-client.ts

const VOICE_ENGINE_URL = process.env.NEXT_PUBLIC_VOICE_ENGINE_URL || "http://localhost:8000";

export async function getReviewByToken(token: string) {
  const res = await fetch(`${VOICE_ENGINE_URL}/api/v1/review/${token}`);
  if (!res.ok) throw new Error("Review not found");
  return res.json();
}

export async function submitClaimReview(
  token: string,
  claimId: string,
  review: {
    status: "approved" | "adjusted" | "rejected";
    adjustedLevel?: number;
    notes?: string;
  }
) {
  const res = await fetch(`${VOICE_ENGINE_URL}/api/v1/review/${token}/claims/${claimId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(review),
  });
  if (!res.ok) throw new Error("Failed to submit review");
  return res.json();
}

export async function submitFinalReview(token: string) {
  const res = await fetch(`${VOICE_ENGINE_URL}/api/v1/review/${token}/submit`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to submit final review");
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

## 3. Acceptance Criteria

- [ ] Dashboard: `/assessments` shows a paginated list of assessments (read-only, no trigger form).
- [ ] Dashboard: `/assessments` supports filtering by status, candidate email, and date range.
- [ ] Dashboard: `/assessments/[id]` shows assessment detail with transcript and recording.
- [ ] Review: `/review/[token]` loads the correct report for a valid token.
- [ ] Review: `/review/[token]` shows 404 for invalid/expired tokens.
- [ ] Review: Claims are displayed with verbatim quote, interpretation, and AI mapping.
- [ ] Review: SME can approve a claim with one click.
- [ ] Review: SME can adjust a claim's level and provide notes.
- [ ] Review: SME can reject a claim with optional notes.
- [ ] Review: Progress indicator updates as claims are reviewed.
- [ ] Review: Skill summary table updates in real time as claims are reviewed.
- [ ] Review: "Submit Final Assessment" is only enabled when all claims are reviewed.
- [ ] Review: Final submission updates the report status and timestamps.
- [ ] Responsive: Review portal is usable on 768px+ screens.
- [ ] Accessibility: All form elements have labels; keyboard navigation works.

## 4. Dependencies

- **Phase 1**: Next.js shell, shared types.
- **Phase 4**: Report generation (produces the data displayed in the review portal).
- **External**: Voice engine API must be running for API calls.

## 5. Risks

| Risk | Mitigation |
|------|------------|
| SME experience confusing | User testing with real SFIA practitioners; iterate on layout |
| Review link sharing (unintended access) | NanoID entropy is sufficient; add optional PIN in v2 |
| Large number of claims per assessment | Pagination + sequential review mode |
| Network errors during review submission | Optimistic UI with retry; save review state locally |
