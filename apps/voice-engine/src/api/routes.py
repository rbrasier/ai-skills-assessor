"""FastAPI routers for the voice engine.

Phase 1 only ships ``/health`` and a stub ``/api/v1/assessment/trigger`` so
the Next.js frontend can integration-check end-to-end. The trigger handler
returns a synthetic ``pending`` session — no real call is placed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

router = APIRouter()


@router.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


class AssessmentTriggerPayload(BaseModel):
    phone_number: str = Field(..., description="E.164 phone number, e.g. +61412345678")
    candidate_id: str = Field(..., description="UUID of the candidate")


class AssessmentTriggerResult(BaseModel):
    session_id: str
    status: str
    created_at: str


@router.post(
    "/api/v1/assessment/trigger",
    tags=["assessment"],
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AssessmentTriggerResult,
)
async def trigger_assessment(payload: AssessmentTriggerPayload) -> AssessmentTriggerResult:
    return AssessmentTriggerResult(
        session_id=str(uuid4()),
        status="pending",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
