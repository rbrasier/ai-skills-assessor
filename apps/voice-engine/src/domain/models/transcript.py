"""Transcript domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TranscriptSegment:
    timestamp: datetime
    speaker: str  # "candidate" | "bot"
    text: str
    duration_seconds: float


@dataclass
class Transcript:
    id: str
    session_id: str
    raw_text: str
    segments: list[TranscriptSegment] = field(default_factory=list)
    language: str = "en"
    created_at: datetime | None = None
