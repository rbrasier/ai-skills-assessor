# Assessment Report Contract Specification

## Status
Draft

## Date
2026-04-16

## References
- PRD-001: Voice-AI SFIA Skills Assessment Platform
- Phase 4: Claim Extraction Pipeline
- Phase 5: SME Review Portal

## Purpose

This document defines the shared data contracts between the Voice Engine (Python), the Next.js frontend (TypeScript), and the PostgreSQL database. These types are the single source of truth — both the TypeScript types in `packages/shared-types` and the Pydantic models in `apps/voice-engine` must conform to these schemas.

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
    "sme_status": {
      "type": "string",
      "enum": ["pending", "approved", "adjusted", "rejected"],
      "default": "pending"
    },
    "sme_adjusted_level": {
      "type": "integer",
      "minimum": 1,
      "maximum": 7,
      "description": "SME-adjusted level (only if status is 'adjusted')"
    },
    "sme_notes": {
      "type": "string",
      "description": "SME reviewer notes"
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
  "required": ["id", "session_id", "review_token", "candidate_name", "skill_summaries", "total_claims", "overall_confidence", "generated_at", "status"],
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid"
    },
    "session_id": {
      "type": "string",
      "format": "uuid"
    },
    "review_token": {
      "type": "string",
      "minLength": 21,
      "maxLength": 21,
      "description": "NanoID token for secure review access"
    },
    "review_url": {
      "type": "string",
      "format": "uri",
      "description": "Full URL for SME review"
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
    "sme_reviewed_at": {
      "type": "string",
      "format": "date-time"
    },
    "status": {
      "type": "string",
      "enum": ["generated", "sent", "in_review", "completed"]
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

## 6. SME Review Actions

### Claim Review Request

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ClaimReviewRequest",
  "type": "object",
  "required": ["status"],
  "properties": {
    "status": {
      "type": "string",
      "enum": ["approved", "adjusted", "rejected"]
    },
    "adjusted_level": {
      "type": "integer",
      "minimum": 1,
      "maximum": 7,
      "description": "Required when status is 'adjusted'"
    },
    "notes": {
      "type": "string",
      "description": "Optional reviewer notes"
    }
  }
}
```

### Final Review Submission Response

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "FinalReviewResponse",
  "type": "object",
  "required": ["session_id", "status", "reviewed_at"],
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid"
    },
    "status": {
      "type": "string",
      "enum": ["completed"]
    },
    "reviewed_at": {
      "type": "string",
      "format": "date-time"
    },
    "summary": {
      "type": "object",
      "properties": {
        "total_claims": {"type": "integer"},
        "approved": {"type": "integer"},
        "adjusted": {"type": "integer"},
        "rejected": {"type": "integer"}
      }
    }
  }
}
```

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

export type ReportStatus = "generated" | "sent" | "in_review" | "completed";

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
  sme_status: ClaimSMEStatus;
  sme_adjusted_level?: number;
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
  review_token: string;
  review_url: string;
  candidate_name: string;
  skill_summaries: SkillSummary[];
  total_claims: number;
  overall_confidence: number;
  generated_at: string;
  sme_reviewed_at?: string;
  status: ReportStatus;
  expires_at: string;
}

export interface ClaimReviewRequest {
  status: "approved" | "adjusted" | "rejected";
  adjusted_level?: number;
  notes?: string;
}

export interface FinalReviewResponse {
  session_id: string;
  status: "completed";
  reviewed_at: string;
  summary: {
    total_claims: number;
    approved: number;
    adjusted: number;
    rejected: number;
  };
}
```

---

## 8. API Endpoints Summary

| Method | Path | Request | Response | Auth |
|--------|------|---------|----------|------|
| `POST` | `/api/v1/assessment/trigger` | `AssessmentTriggerRequest` | `AssessmentTriggerResponse` | API Key |
| `GET` | `/api/v1/assessment/{session_id}/status` | — | `AssessmentSession` | API Key |
| `POST` | `/api/v1/assessment/{session_id}/process` | — | `{ review_url, total_claims, ... }` | API Key |
| `GET` | `/api/v1/assessment/{session_id}/report` | — | `AssessmentReport` | API Key |
| `GET` | `/api/v1/review/{token}` | — | `AssessmentReport` | Token (public) |
| `PATCH` | `/api/v1/review/{token}/claims/{claim_id}` | `ClaimReviewRequest` | `Claim` (updated) | Token (public) |
| `POST` | `/api/v1/review/{token}/submit` | — | `FinalReviewResponse` | Token (public) |

---

## 9. Versioning

- All API endpoints are versioned under `/api/v1/`.
- JSON schemas include `$schema` for validation tooling.
- Breaking changes to the contract require a new API version (`/api/v2/`).
- Additive changes (new optional fields) are backward-compatible and do not require versioning.
