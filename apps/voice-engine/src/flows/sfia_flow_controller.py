"""SFIA assessment flow controller — Pipecat Flows state machine (stub).

Will encode: Introduction → Skill Discovery → Evidence Gathering → Closing.
Implemented in the voice-engine core phase once Pipecat Flows is wired up.
"""

from __future__ import annotations


class SfiaFlowController:
    """Placeholder for the Pipecat Flows-based SFIA interview state machine."""

    def __init__(self) -> None:
        pass

    async def start(self) -> None:
        raise NotImplementedError("SfiaFlowController.start is implemented in Phase 2")
