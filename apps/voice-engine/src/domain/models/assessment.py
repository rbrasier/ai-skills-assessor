"""Assessment session and call-related domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AssessmentStatus(str, Enum):
    PENDING = "pending"
    DIALLING = "dialling"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CallConfig:
    """Inputs required to place an outbound assessment call."""

    phone_number: str
    candidate_id: str
    timeout_seconds: int = 300


@dataclass
class CallConnection:
    """Live transport-level handle returned by ``IVoiceTransport.dial``."""

    connection_id: str
    room_url: str
    is_active: bool


@dataclass
class AssessmentSession:
    """Persistent record of an assessment, mirroring the DB row."""

    id: str
    candidate_id: str
    phone_number: str
    status: AssessmentStatus
    daily_room_url: str | None = None
    recording_url: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
