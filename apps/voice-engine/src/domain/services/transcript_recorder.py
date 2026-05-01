"""TranscriptRecorder — accumulates speaker turns during an assessment call.

Pure Python (no Pipecat dependency) so it is fully testable in the lean CI
install without the ``[voice]`` extras. The recorder is given to both the
:class:`SfiaFlowController` (which updates the current phase on state
transitions) and the :class:`TranscriptFrameObserver` (which calls
``record_turn`` as frames flow through the Pipecat pipeline).

Usage::

    recorder = TranscriptRecorder()
    recorder.record_turn(speaker="bot", text="Hi, I'm Noa…")
    recorder.set_phase("skill_discovery")
    recorder.record_turn(speaker="candidate", text="I lead the platform team.")
    await recorder.finalize(session_id, persistence, identified_skills=[...])
"""

from __future__ import annotations

import dataclasses
import logging
import time
from typing import TYPE_CHECKING, Any

from src.domain.models.transcript import TranscriptTurn

if TYPE_CHECKING:
    from src.domain.ports.persistence import IPersistence

logger = logging.getLogger(__name__)


class TranscriptRecorder:
    """Accumulates :class:`TranscriptTurn` objects throughout a call.

    Thread-safety: ``record_turn`` and ``set_phase`` are called from the
    Pipecat event loop (single-threaded), so no locking is needed.
    """

    def __init__(self) -> None:
        self._turns: list[TranscriptTurn] = []
        self._current_phase: str = "introduction"

    # ─── Phase tracking ──────────────────────────────────────────────

    def set_phase(self, phase: str) -> None:
        """Update the flow phase label applied to subsequent turns."""
        logger.debug("TranscriptRecorder: phase → %s", phase)
        self._current_phase = phase

    @property
    def current_phase(self) -> str:
        return self._current_phase

    # ─── Turn accumulation ───────────────────────────────────────────

    def record_turn(
        self,
        *,
        speaker: str,
        text: str,
        vad_confidence: float | None = None,
    ) -> None:
        """Append a speaker turn tagged with the current phase."""
        text = text.strip()
        if not text:
            return
        turn = TranscriptTurn(
            timestamp=time.time(),
            speaker=speaker,  # type: ignore[arg-type]
            text=text,
            phase=self._current_phase,
            vad_confidence=vad_confidence,
        )
        self._turns.append(turn)
        logger.debug(
            "TranscriptRecorder: [%s/%s] %s",
            speaker,
            self._current_phase,
            text[:80],
        )

    # ─── Serialisation ───────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Return the transcript as a JSON-serialisable dict.

        Structure::

            {
                "turns": [
                    {
                        "timestamp": 1714344000.123,
                        "speaker": "bot",
                        "text": "Hello, I'm Noa…",
                        "phase": "introduction",
                        "vad_confidence": null
                    },
                    …
                ]
            }
        """
        return {"turns": [dataclasses.asdict(t) for t in self._turns]}

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    def snippet(self, max_chars: int = 500) -> str:
        """Return the first ``max_chars`` characters of the assembled transcript."""
        lines = [f"[{t.speaker}/{t.phase}] {t.text}" for t in self._turns]
        full = "\n".join(lines)
        return full[:max_chars]

    # ─── Persistence ─────────────────────────────────────────────────

    async def finalize(
        self,
        session_id: str,
        persistence: IPersistence,
        *,
        identified_skills: list[dict[str, Any]] | None = None,
        recording_duration_seconds: int | None = None,
    ) -> None:
        """Persist transcript to the dedicated transcript_json column (Phase 6+).

        Writes the transcript dict to ``assessment_sessions.transcript_json``
        via ``persistence.save_transcript()``. Remaining metadata fields
        (identified_skills, recording_duration_seconds) are merged via
        ``persistence.merge_session_metadata()`` as before.
        """
        try:
            await persistence.save_transcript(session_id, self.to_dict())
            logger.info(
                "TranscriptRecorder: saved %d turns for session %s",
                self.turn_count,
                session_id,
            )
        except Exception:
            logger.exception(
                "TranscriptRecorder: failed to save transcript for session %s",
                session_id,
            )

        extra: dict[str, Any] = {}
        if identified_skills is not None:
            extra["identified_skills"] = identified_skills
        if recording_duration_seconds is not None:
            extra["recording_duration_seconds"] = recording_duration_seconds

        if extra:
            try:
                await persistence.merge_session_metadata(session_id, extra)
            except Exception:
                logger.exception(
                    "TranscriptRecorder: failed to merge metadata for session %s",
                    session_id,
                )


__all__ = ["TranscriptRecorder"]
