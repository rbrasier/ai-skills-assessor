"""Transcript domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class TranscriptTurn:
    """One speaker turn captured during an assessment call (Phase 4)."""

    timestamp: float                        # Unix timestamp when turn started
    speaker: Literal["candidate", "bot"]
    text: str                               # Exact text spoken
    phase: str                              # Flow state: "introduction", "skill_discovery", etc.
    vad_confidence: float | None = None     # VAD confidence 0.0–1.0 where available


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
