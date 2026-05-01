# Phase 6 Revision: Dual expert/supervisor review tokens

## Status
Planning / optional extension

## Date
2026-05-01

## Purpose

**Baseline Phase 6** (see [`phase-6-claim-extraction-pipeline.md`](phase-6-claim-extraction-pipeline.md)) ships a single `review_token`, `GET /api/v1/review/{token}`, and claim fields `sme_status` / `sme_adjusted_level` / `sme_notes`.

This document captures the **revision** required for the **dual reviewer** product model (expert vs supervisor modal URLs, separate NanoIDs, split `PUT` APIs). Apply it **after** baseline Phase 6 lands, or fold into implementation **before** Phase 7 UI if both are built together.

Normative payload shapes and enums are in [Assessment Report Contract](../contracts/assessment-report-contract.md).

---

## 1. Domain models (`claim.py`)

Replace single-role SME fields on `Claim` with:

```python
expert_level: int | None = Field(default=None, ge=1, le=7)
supervisor_decision: str = "pending"   # pending | verified | rejected
supervisor_comment: str | None = None   # required on supervisor submit per row
```

Migrate legacy `sme_*` into `expert_level` / supervisor fields where applicable, or one-off JSON migration on `claims_json`.

Update `AssessmentReport` (in-memory) to carry:

- `expert_review_token`, `supervisor_review_token`
- `expert_review_url`, `supervisor_review_url` (`{base_url}/review/expert/{token}`, `{base_url}/review/supervisor/{token}`)
- Use `report_status` workflow values aligned with the contract (`awaiting_expert`, `awaiting_supervisor`, `reviews_complete`, …).

---

## 2. Database (`assessment_sessions`)

Add or migrate columns:

| Column | Purpose |
|--------|---------|
| `expert_review_token` | VARCHAR(21) UNIQUE |
| `supervisor_review_token` | VARCHAR(21) UNIQUE |
| `expert_submitted_at`, `expert_reviewer_name`, `expert_reviewer_email` | Expert audit |
| `supervisor_submitted_at`, `supervisor_reviewer_name`, `supervisor_reviewer_email` | Supervisor audit |
| `reviews_completed_at` | Set when both roles submitted |

Extend `report_status` length/enum as needed.

**Deprecation:** `review_token` (single) — migrate rows or dual-write during transition; drop after migration.

Partial indexes on both token columns (WHERE NOT NULL).

**Version bump:** MINOR migration when adding columns (e.g. `v0_6_1_dual_review_tokens` or next MINOR after baseline Phase 6).

---

## 3. `ReportGenerator.generate()`

- Generate **two** NanoIDs (same alphabet/length as today).
- Persist both via `save_report(...)` (signature extended below).
- Return both URLs on the `AssessmentReport` object.

---

## 4. `IPersistence` extensions

Extend beyond baseline Phase 6:

- `save_report(..., expert_review_token, supervisor_review_token, ...)` (replace single `review_token` parameter).
- `get_report_by_expert_token(token)` / `get_report_by_supervisor_token(token)` instead of (or in addition to) `get_report_by_token`.
- `save_expert_review(token, reviewer_full_name, reviewer_email, claims_patch)` — merge `expert_level` by claim `id`; set expert audit columns; advance `report_status`.
- `save_supervisor_review(...)` — merge `supervisor_decision` + `supervisor_comment`; set supervisor audit + `reviews_completed_at` when expert already submitted.

Implementations: `InMemoryPersistence`, `PostgresPersistence`.

---

## 5. FastAPI routes

Replace single public review route with:

| Method | Path |
|--------|------|
| `GET` | `/api/v1/review/expert/{token}` |
| `PUT` | `/api/v1/review/expert/{token}` |
| `GET` | `/api/v1/review/supervisor/{token}` |
| `PUT` | `/api/v1/review/supervisor/{token}` |

Request/response bodies: contract §6 (`ExpertReviewSubmitPayload`, `SupervisorReviewSubmitPayload`, `ReviewSaveResponse`).

`POST /api/v1/assessment/{session_id}/process` response should include `expert_review_url` and `supervisor_review_url`.

Duplicate submit for same role → **409** recommended.

---

## 6. Notifications

Extend `INotificationSender` stub to deliver **both** links (expert + supervisor), or separate calls — product dependent.

---

## 7. Acceptance criteria (incremental)

- [ ] Both tokens unique per session; either invalid/expired → 404.
- [ ] Expert `PUT` updates only expert fields on claims + expert audit columns.
- [ ] Supervisor `PUT` updates only supervisor fields + supervisor audit columns.
- [ ] `reviews_completed_at` set only after **both** successful saves.
- [ ] Contract tests or OpenAPI snapshot matches [Assessment Report Contract](../contracts/assessment-report-contract.md).

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-01 | Split from main Phase 6 doc while Phase 6 implementation is in progress; dual-token model for Phase 7 |
