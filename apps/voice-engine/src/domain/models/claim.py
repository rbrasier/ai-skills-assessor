"""Stub claim models for forward-compatibility.

Phase 1 does not implement claim extraction; these dataclasses are placeholders
so type-checkers and adapters can depend on stable identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Claim:
    id: str
    session_id: str
    text: str


@dataclass
class ClaimMapping:
    claim_id: str
    framework: str  # e.g. "SFIA"
    skill_code: str
    level: int
    confidence: float
