"""Assessment session and call-related domain models.

Phase 2 additions:
  * ``Candidate`` — mirror of the DB ``candidates`` row (email PK).
  * ``AssessmentSession.metadata`` — free-form JSON dict, currently used
    for ``failureReason`` and ``cancelledAt`` but kept open for future
    extensions.
  * ``CallConfig`` / ``CallConnection`` are the transport-level
    request/response shapes used by ``IVoiceTransport``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AssessmentStatus(str, Enum):
    PENDING = "pending"
    DIALLING = "dialling"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Candidate:
    """Mirrors the ``candidates`` row. Email is the primary key."""

    email: str
    first_name: str
    last_name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass
class CallConfig:
    """Inputs required to place an outbound assessment call."""

    session_id: str
    phone_number: str
    candidate_id: str
    region: str = "ap-southeast-2"
    timeout_seconds: int = 300


@dataclass
class CallConnection:
    """Live transport-level handle returned by ``IVoiceTransport.dial``."""

    session_id: str
    connection_id: str
    room_url: str
    is_active: bool
    started_at: datetime | None = None
    ended_at: datetime | None = None


@dataclass
class AssessmentSession:
    """Persistent record of an assessment, mirroring the DB row."""

    id: str
    candidate_id: str
    phone_number: str
    status: AssessmentStatus
    metadata: dict[str, Any] = field(default_factory=dict)
    daily_room_url: str | None = None
    recording_url: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime | None = None
