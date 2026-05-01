# Assessment Report Contract Specification

## Status
Draft

## Date
2026-05-01

## References
- PRD-001: Voice-AI SFIA Skills Assessment Platform
- Phase 6: Claim Extraction Pipeline (report generation, dual review tokens)
- Phase 7: Expert & Supervisor Review (Next.js modal surfaces)

## Purpose

This document defines the shared data contracts between the Voice Engine (Python), the Next.js frontend (TypeScript), and the PostgreSQL database. These types are the single source of truth — both the TypeScript types in `packages/shared-types` and the Pydantic models in `apps/voice-engine` must conform to these schemas.

**Human review model:** Two independent NanoID URLs — **expert** (endorse/adjust SFIA levels per claim) and **supervisor** (verify/reject claims register + comment per row). Final HR/export outcome is allowed only after **both** submissions succeed (see PRD-001 §4.4).

---

## 1. Assessment Trigger

### Request

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AssessmentTriggerRequest",
  "type": "object",
  "required": ["phone_number", "candidate_id"],
  "properties": {
    "phone_number": {
      "type": "string",
      "pattern": "^\\+61\\d{9}$",
      "description": "Australian phone number in E.164 format"
    },
    "candidate_id": {
      "type": "string",
      "format": "uuid",
      "description": "UUID of the candidate record"
    },
    "sme_email": {
      "type": "string",
      "format": "email",
      "description": "Optional email for the SME reviewer"
    },
    "framework_type": {
      "type": "string",
      "default": "sfia-9",
      "description": "Assessment framework to use"
    }
  }
}
```

### Response

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AssessmentTriggerResponse",
  "type": "object",
  "required": ["session_id", "status"],
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid"
    },
    "status": {
      "type": "string",
      "enum": ["dialling", "error"]
    },
    "error": {
      "type": "string",
      "description": "Error message if status is 'error'"
    }
  }
}
```

---

## 2. Assessment Session

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AssessmentSession",
  "type": "object",
  "required": ["id", "candidate_id", "status", "created_at"],
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid"
    },
    "candidate_id": {
      "type": "string",
      "format": "uuid"
    },
    "status": {
      "type": "string",
      "enum": ["pending", "dialling", "in_progress", "completed", "processed", "failed", "cancelled"]
    },
    "triggered_by": {
      "type": "string",
      "format": "uuid"
    },
    "daily_room_url": {
      "type": "string",
      "format": "uri"
    },
    "recording_url": {
      "type": "string",
      "format": "uri"
    },
    "started_at": {
      "type": "string",
      "format": "date-time"
    },
    "ended_at": {
      "type": "string",
      "format": "date-time"
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

---

## 3. Transcript

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Transcript",
  "type": "object",
  "required": ["id", "session_id", "full_text", "segments"],
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid"
    },
    "session_id": {
      "type": "string",
      "format": "uuid"
    },
    "full_text": {
      "type": "string",
      "description": "Complete transcript as plain text"
    },
    "segments": {
      "type": "array",
      "items": {
        "$ref": "#/definitions/TranscriptSegment"
      }
    },
    "duration_seconds": {
      "type": "number",
      "description": "Total call duration in seconds"
    }
  },
  "definitions": {
    "TranscriptSegment": {
      "type": "object",
      "required": ["speaker", "text", "start_time", "end_time"],
      "properties": {
        "speaker": {
          "type": "string",
          "enum": ["candidate", "bot"]
        },
        "text": {
          "type": "string"
        },
        "start_time": {
          "type": "number",
          "description": "Seconds from call start"
        },
        "end_time": {
          "type": "number",
          "description": "Seconds from call start"
        }
      }
    }
  }
}
```

---

## 4. Claim

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Claim",
  "type": "object",
  "required": ["id", "session_id", "verbatim_quote", "interpreted_claim", "sfia_skill_code", "sfia_level", "confidence"],
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid"
    },
    "session_id": {
      "type": "string",
      "format": "uuid"
    },
    "verbatim_quote": {
      "type": "string",
      "description": "Exact words from the transcript"
    },
    "interpreted_claim": {
      "type": "string",
      "description": "AI's interpretation of the claim"
    },
    "sfia_skill_code": {
      "type": "string",
      "description": "SFIA skill code (e.g., PROG, ITMG, TEST)"
    },
    "sfia_skill_name": {
      "type": "string",
      "description": "Full SFIA skill name"
    },
    "sfia_level": {
      "type": "integer",
      "minimum": 1,
      "maximum": 7,
      "description": "SFIA responsibility level"
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "description": "AI confidence in the skill/level mapping (0.0 to 1.0)"
    },
    "reasoning": {
      "type": "string",
      "description": "AI's reasoning for the mapping"
    },
    "expert_level": {
      "type": ["integer", "null"],
      "minimum": 1,
      "maximum": 7,
      "description": "Expert-endorsed or adjusted SFIA level (null until expert saves)"
    },
    "supervisor_decision": {
      "type": "string",
      "enum": ["pending", "verified", "rejected"],
      "default": "pending",
      "description": "Supervisor disposition for this claims-register row"
    },
    "supervisor_comment": {
      "type": ["string", "null"],
      "description": "Supervisor comment — required for every row when supervisor submits (including verified)"
    },
    "sme_status": {
      "type": "string",
      "enum": ["pending", "approved", "adjusted", "rejected"],
      "description": "Deprecated — use expert_level + supervisor_decision. Retained for backward compatibility during migration."
    },
    "sme_adjusted_level": {
      "type": "integer",
      "minimum": 1,
      "maximum": 7,
      "description": "Deprecated — use expert_level"
    },
    "sme_notes": {
      "type": "string",
      "description": "Deprecated — use supervisor_comment where applicable"
    }
  }
}
```

---

## 5. Assessment Report

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AssessmentReport",
  "type": "object",
  "required": ["id", "session_id", "expert_review_token", "supervisor_review_token", "candidate_name", "skill_summaries", "total_claims", "overall_confidence", "generated_at", "status"],
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid"
    },
    "session_id": {
      "type": "string",
      "format": "uuid"
    },
    "expert_review_token": {
      "type": "string",
      "minLength": 21,
      "maxLength": 21,
      "description": "NanoID for expert/SME modal URL"
    },
    "supervisor_review_token": {
      "type": "string",
      "minLength": 21,
      "maxLength": 21,
      "description": "NanoID for supervisor modal URL"
    },
    "expert_review_url": {
      "type": "string",
      "format": "uri",
      "description": "Full URL for expert review"
    },
    "supervisor_review_url": {
      "type": "string",
      "format": "uri",
      "description": "Full URL for supervisor review"
    },
    "review_token": {
      "type": "string",
      "minLength": 21,
      "maxLength": 21,
      "description": "Deprecated — use expert_review_token + supervisor_review_token"
    },
    "review_url": {
      "type": "string",
      "format": "uri",
      "description": "Deprecated"
    },
    "candidate_name": {
      "type": "string"
    },
    "skill_summaries": {
      "type": "array",
      "items": {
        "$ref": "#/definitions/SkillSummary"
      }
    },
    "total_claims": {
      "type": "integer",
      "minimum": 0
    },
    "overall_confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1
    },
    "generated_at": {
      "type": "string",
      "format": "date-time"
    },
    "expert_submitted_at": {
      "type": "string",
      "format": "date-time",
      "description": "When expert PUT succeeded"
    },
    "expert_reviewer_full_name": {
      "type": "string",
      "description": "Declared at expert save"
    },
    "expert_reviewer_email": {
      "type": "string",
      "format": "email"
    },
    "supervisor_submitted_at": {
      "type": "string",
      "format": "date-time"
    },
    "supervisor_reviewer_full_name": {
      "type": "string"
    },
    "supervisor_reviewer_email": {
      "type": "string",
      "format": "email"
    },
    "reviews_completed_at": {
      "type": "string",
      "format": "date-time",
      "description": "When both expert and supervisor submissions exist"
    },
    "sme_reviewed_at": {
      "type": "string",
      "format": "date-time",
      "description": "Deprecated — use reviews_completed_at or role-specific timestamps"
    },
    "status": {
      "type": "string",
      "enum": [
        "generated",
        "sent",
        "awaiting_expert",
        "awaiting_supervisor",
        "reviews_complete",
        "in_review",
        "completed"
      ],
      "description": "Workflow status — prefer awaiting_* / reviews_complete for Phase 7; in_review/completed retained for compatibility"
    },
    "expires_at": {
      "type": "string",
      "format": "date-time"
    }
  },
  "definitions": {
    "SkillSummary": {
      "type": "object",
      "required": ["skill_code", "skill_name", "claim_count", "suggested_level", "average_confidence"],
      "properties": {
        "skill_code": {
          "type": "string"
        },
        "skill_name": {
          "type": "string"
        },
        "claim_count": {
          "type": "integer",
          "minimum": 0
        },
        "suggested_level": {
          "type": "integer",
          "minimum": 1,
          "maximum": 7
        },
        "average_confidence": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "claims": {
          "type": "array",
          "items": {
            "$ref": "#/definitions/Claim"
          }
        }
      }
    },
    "Claim": {
      "$ref": "#/Claim"
    }
  }
}
```

---

## 6. Expert & Supervisor Review Actions

### Expert review submission (`PUT /api/v1/review/expert/{token}`)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ExpertReviewSubmitPayload",
  "type": "object",
  "required": ["reviewer_full_name", "reviewer_email", "claims"],
  "properties": {
    "reviewer_full_name": {
      "type": "string",
      "minLength": 1,
      "description": "Expert declare-at-submit identity"
    },
    "reviewer_email": {
      "type": "string",
      "format": "email"
    },
    "claims": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["id", "expert_level"],
        "properties": {
          "id": {
            "type": "string",
            "format": "uuid",
            "description": "Claim id from claims_json"
          },
          "expert_level": {
            "type": "integer",
            "minimum": 1,
            "maximum": 7,
            "description": "Endorsed or adjusted SFIA level for this row"
          }
        }
      }
    }
  }
}
```

### Supervisor review submission (`PUT /api/v1/review/supervisor/{token}`)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "SupervisorReviewSubmitPayload",
  "type": "object",
  "required": ["reviewer_full_name", "reviewer_email", "claims"],
  "properties": {
    "reviewer_full_name": {
      "type": "string",
      "minLength": 1
    },
    "reviewer_email": {
      "type": "string",
      "format": "email"
    },
    "claims": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["id", "supervisor_decision", "supervisor_comment"],
        "properties": {
          "id": {
            "type": "string",
            "format": "uuid"
          },
          "supervisor_decision": {
            "type": "string",
            "enum": ["verified", "rejected"]
          },
          "supervisor_comment": {
            "type": "string",
            "minLength": 1,
            "description": "Required for every row (verified and rejected)"
          }
        }
      }
    }
  }
}
```

### Review save response (either role)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ReviewSaveResponse",
  "type": "object",
  "required": ["session_id", "report_status"],
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid"
    },
    "report_status": {
      "type": "string",
      "description": "Updated workflow status e.g. awaiting_supervisor | reviews_complete"
    },
    "reviews_completed_at": {
      "type": "string",
      "format": "date-time",
      "description": "Populated when both roles have submitted"
    },
    "claims": {
      "type": "array",
      "description": "Optional echo of updated claims_json rows"
    }
  }
}
```

### Deprecated: single-role claim PATCH

The previous `ClaimReviewRequest` + `PATCH /review/{token}/claims/{id}` model is **deprecated** in favour of the expert/supervisor `PUT` payloads above.

---

## 7. TypeScript Type Definitions

These types are generated from or must match the JSON schemas above.

```typescript
// packages/shared-types/src/assessment-trigger.ts

export interface AssessmentTriggerRequest {
  phone_number: string;
  candidate_id: string;
  sme_email?: string;
  framework_type?: string;
}

export interface AssessmentTriggerResponse {
  session_id: string;
  status: "dialling" | "error";
  error?: string;
}

// packages/shared-types/src/assessment-report.ts

export type SessionStatus = 
  | "pending" | "dialling" | "in_progress" 
  | "completed" | "processed" | "failed" | "cancelled";

export type ClaimSMEStatus = "pending" | "approved" | "adjusted" | "rejected";

/** @deprecated Prefer expert_level + supervisor_decision */
export type ClaimSMEStatusLegacy = ClaimSMEStatus;

export type SupervisorDecisionRow = "pending" | "verified" | "rejected";

export type ReportStatus =
  | "generated"
  | "sent"
  | "awaiting_expert"
  | "awaiting_supervisor"
  | "reviews_complete"
  | "in_review"
  | "completed";

export interface TranscriptSegment {
  speaker: "candidate" | "bot";
  text: string;
  start_time: number;
  end_time: number;
}

export interface Transcript {
  id: string;
  session_id: string;
  full_text: string;
  segments: TranscriptSegment[];
  duration_seconds?: number;
}

export interface Claim {
  id: string;
  session_id: string;
  verbatim_quote: string;
  interpreted_claim: string;
  sfia_skill_code: string;
  sfia_skill_name: string;
  sfia_level: number;
  confidence: number;
  reasoning: string;
  expert_level?: number | null;
  supervisor_decision: SupervisorDecisionRow;
  supervisor_comment?: string | null;
  /** @deprecated */
  sme_status?: ClaimSMEStatus;
  /** @deprecated */
  sme_adjusted_level?: number;
  /** @deprecated */
  sme_notes?: string;
}

export interface SkillSummary {
  skill_code: string;
  skill_name: string;
  claim_count: number;
  suggested_level: number;
  average_confidence: number;
  claims: Claim[];
}

export interface AssessmentReport {
  id: string;
  session_id: string;
  expert_review_token: string;
  supervisor_review_token: string;
  expert_review_url: string;
  supervisor_review_url: string;
  /** @deprecated */
  review_token?: string;
  /** @deprecated */
  review_url?: string;
  candidate_name: string;
  skill_summaries: SkillSummary[];
  total_claims: number;
  overall_confidence: number;
  generated_at: string;
  expert_submitted_at?: string;
  expert_reviewer_full_name?: string;
  expert_reviewer_email?: string;
  supervisor_submitted_at?: string;
  supervisor_reviewer_full_name?: string;
  supervisor_reviewer_email?: string;
  reviews_completed_at?: string;
  /** @deprecated */
  sme_reviewed_at?: string;
  status: ReportStatus;
  expires_at: string;
}

export interface ExpertReviewSubmitPayload {
  reviewer_full_name: string;
  reviewer_email: string;
  claims: Array<{ id: string; expert_level: number }>;
}

export interface SupervisorReviewSubmitPayload {
  reviewer_full_name: string;
  reviewer_email: string;
  claims: Array<{
    id: string;
    supervisor_decision: "verified" | "rejected";
    supervisor_comment: string;
  }>;
}

export interface ReviewSaveResponse {
  session_id: string;
  report_status: ReportStatus;
  reviews_completed_at?: string;
  claims?: Claim[];
}
```

---

## 8. API Endpoints Summary

| Method | Path | Request | Response | Auth |
|--------|------|---------|----------|------|
| `POST` | `/api/v1/assessment/trigger` | `AssessmentTriggerRequest` | `AssessmentTriggerResponse` | API Key |
| `GET` | `/api/v1/assessment/{session_id}/status` | — | `AssessmentSession` | API Key |
| `POST` | `/api/v1/assessment/{session_id}/process` | — | `{ expert_review_url, supervisor_review_url, total_claims, ... }` | API Key |
| `GET` | `/api/v1/assessment/{session_id}/report` | — | `AssessmentReport` | API Key |
| `GET` | `/api/v1/review/expert/{token}` | — | `AssessmentReport` (+ transcript fields per implementation) | Token (public) |
| `PUT` | `/api/v1/review/expert/{token}` | `ExpertReviewSubmitPayload` | `ReviewSaveResponse` | Token (public) |
| `GET` | `/api/v1/review/supervisor/{token}` | — | `AssessmentReport` (+ transcript) | Token (public) |
| `PUT` | `/api/v1/review/supervisor/{token}` | `SupervisorReviewSubmitPayload` | `ReviewSaveResponse` | Token (public) |

Duplicate submit for the same role → **409 Conflict** (recommended).

---

## 9. Versioning

- All API endpoints are versioned under `/api/v1/`.
- JSON schemas include `$schema` for validation tooling.
- Breaking changes to the contract require a new API version (`/api/v2/`).
- Additive changes (new optional fields) are backward-compatible and do not require versioning.
