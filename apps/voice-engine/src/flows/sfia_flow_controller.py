"""SFIA assessment flow controller — Pipecat Flows 5-state machine.

Implements the full Introduction → SkillDiscovery → EvidenceGathering →
Summary → Closing flow using pipecat-ai-flows ``FlowsFunctionSchema`` and
``FlowManager``.

Design principles
-----------------
* **Handlers are public methods** so they can be unit-tested directly without
  needing Pipecat installed (lean CI).
* **Node builders use lazy imports** — ``FlowsFunctionSchema`` is only imported
  when ``get_initial_node()`` is called (inside the Pipecat pipeline, which
  already has the [voice] extras).
* **Phase tracking is decoupled** — handlers call ``recorder.set_phase()`` so
  the :class:`TranscriptFrameObserver` always knows which flow state produced
  each speaker turn.

pipecat-ai-flows API (v0.0.10+)
--------------------------------
Each state is a ``NodeConfig`` dict with:
  - ``role_message`` (str): Persona / system instruction for the LLM.
  - ``task_messages`` (list[dict]): Per-node task prompt.
  - ``functions`` (list[FlowsFunctionSchema]): Available function calls.

Handlers signature: ``async (args: dict, flow_manager: Any) -> tuple[Any, NodeConfig | None]``
Return ``(None, next_node_config)`` to transition, or ``(None, None)`` to stay.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from src.domain.services.transcript_recorder import TranscriptRecorder

logger = logging.getLogger(__name__)

_BOT_PERSONA = (
    "You are Noa, a warm and professional AI skills assessor from Resonant. "
    "You conduct structured SFIA-based skills assessments over the phone. "
    "Keep your language conversational, concise, and encouraging. "
    "Never mention SFIA skill codes or numerical levels to the candidate — "
    "keep the conversation natural. "
    "When you have enough information to call a transition function, do so promptly."
)


class SfiaFlowController:
    """Stateful controller for the 5-node SFIA assessment conversation flow.

    Owns the flow configuration and function handlers. Wired into the Pipecat
    pipeline by :func:`~src.flows.assessment_pipeline.build_sfia_pipeline`.
    """

    def __init__(
        self,
        *,
        recorder: TranscriptRecorder,
        on_call_ended: Callable[[], Awaitable[None] | None],
    ) -> None:
        self._recorder = recorder
        self._on_call_ended = on_call_ended
        self._identified_skills: list[dict[str, Any]] = []

    @property
    def identified_skills(self) -> list[dict[str, Any]]:
        return list(self._identified_skills)

    # ─── Public handlers (testable without Pipecat) ──────────────────
    #
    # Handlers perform two tasks:
    #   1. Pure side-effects (phase tracking, skill storage) — always run.
    #   2. Return the next NodeConfig — requires pipecat-ai-flows [voice] extras.
    #      Falls back to None when the package is not installed (lean CI).

    async def handle_consent_given(
        self, args: dict[str, Any], flow_manager: Any
    ) -> tuple[None, Any]:
        """Candidate consents — transition to SkillDiscovery."""
        logger.info("SfiaFlow: consent_given → skill_discovery")
        self._recorder.set_phase("skill_discovery")
        return None, _try_build(self._build_skill_discovery_node)

    async def handle_consent_declined(
        self, args: dict[str, Any], flow_manager: Any
    ) -> tuple[None, Any]:
        """Candidate declines — skip to Closing."""
        logger.info("SfiaFlow: consent_declined → closing")
        self._recorder.set_phase("closing")
        return None, _try_build(self._build_closing_node)

    async def handle_skills_identified(
        self, args: dict[str, Any], flow_manager: Any
    ) -> tuple[None, Any]:
        """Skills extracted from SkillDiscovery — transition to EvidenceGathering."""
        skills = args.get("skills", [])
        self._identified_skills = skills
        logger.info("SfiaFlow: skills_identified (%d) → evidence_gathering", len(skills))
        self._recorder.set_phase("evidence_gathering")
        return None, _try_build(self._build_evidence_gathering_node)

    async def handle_evidence_complete(
        self, args: dict[str, Any], flow_manager: Any
    ) -> tuple[None, Any]:
        """Sufficient evidence gathered — transition to Summary."""
        logger.info("SfiaFlow: evidence_complete → summary")
        self._recorder.set_phase("summary")
        return None, _try_build(self._build_summary_node)

    async def handle_summary_complete(
        self, args: dict[str, Any], flow_manager: Any
    ) -> tuple[None, Any]:
        """Summary delivered — transition to Closing."""
        logger.info("SfiaFlow: summary_complete → closing")
        self._recorder.set_phase("closing")
        return None, _try_build(self._build_closing_node)

    async def handle_end_call(
        self, args: dict[str, Any], flow_manager: Any
    ) -> tuple[None, None]:
        """Call complete — trigger transcript finalisation and pipeline teardown."""
        logger.info("SfiaFlow: call_ended — finalising session")
        try:
            result = self._on_call_ended()
            if isinstance(result, Awaitable):
                await result
        except Exception:
            logger.exception("SfiaFlow: on_call_ended callback raised")
        return None, None

    # ─── Entry point ─────────────────────────────────────────────────

    def get_initial_node(self) -> Any:
        """Return the Introduction ``NodeConfig`` to seed ``FlowManager.initialize``."""
        return self._build_introduction_node()

    # ─── Node builders (require pipecat-ai-flows [voice] extras) ─────

    def _build_introduction_node(self) -> Any:
        FlowsFunctionSchema = _import_flows_schema()
        return {
            "role_message": _BOT_PERSONA,
            "task_messages": [
                {
                    "role": "user",
                    "content": (
                        "Introduce yourself as Noa, an AI skills assessor from Resonant. "
                        "Explain briefly (2-3 sentences) that you are conducting a "
                        "structured skills assessment based on the SFIA framework and "
                        "that the conversation will be recorded for review. "
                        "Ask for the candidate's verbal consent to proceed. "
                        "If they agree, call consent_given. "
                        "If they decline for any reason, call consent_declined."
                    ),
                }
            ],
            "functions": [
                FlowsFunctionSchema(
                    name="consent_given",
                    description=(
                        "Candidate has verbally agreed to proceed with the assessment "
                        "and to have the call recorded."
                    ),
                    properties={},
                    required=[],
                    handler=self.handle_consent_given,
                ),
                FlowsFunctionSchema(
                    name="consent_declined",
                    description=(
                        "Candidate has declined to proceed or to be recorded. "
                        "End the call gracefully and thank them for their time."
                    ),
                    properties={},
                    required=[],
                    handler=self.handle_consent_declined,
                ),
            ],
        }

    def _build_skill_discovery_node(self) -> Any:
        FlowsFunctionSchema = _import_flows_schema()
        return {
            "role_message": _BOT_PERSONA,
            "task_messages": [
                {
                    "role": "user",
                    "content": (
                        "Ask the candidate to describe their current role, key "
                        "responsibilities, and areas of IT expertise. "
                        "Keep the conversation natural and curious — do not name or "
                        "reference SFIA codes. "
                        "Listen for mentions of 2-5 distinct skill areas "
                        "(e.g. software development, data engineering, cloud infrastructure, "
                        "project management, security). "
                        "Once you have identified the skill areas from the conversation, "
                        "call skills_identified with the list."
                    ),
                }
            ],
            "functions": [
                FlowsFunctionSchema(
                    name="skills_identified",
                    description=(
                        "Record the skill areas identified from the candidate's "
                        "description of their role. Move to evidence gathering."
                    ),
                    properties={
                        "skills": {
                            "type": "array",
                            "description": "List of skill areas identified",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "skill_code": {
                                        "type": "string",
                                        "description": (
                                            "Short SFIA-style code for the skill area, "
                                            "e.g. PROG, DENG, CLOP, SCTY"
                                        ),
                                    },
                                    "skill_name": {
                                        "type": "string",
                                        "description": (
                                            "Human-readable skill name, "
                                            "e.g. 'Software Development', 'Data Engineering'"
                                        ),
                                    },
                                },
                                "required": ["skill_code", "skill_name"],
                            },
                        }
                    },
                    required=["skills"],
                    handler=self.handle_skills_identified,
                ),
            ],
        }

    def _build_evidence_gathering_node(self) -> Any:
        FlowsFunctionSchema = _import_flows_schema()

        skills_summary = ", ".join(
            s.get("skill_name", s.get("skill_code", "unknown"))
            for s in self._identified_skills
        ) or "the areas discussed"

        return {
            "role_message": _BOT_PERSONA,
            "task_messages": [
                {
                    "role": "user",
                    "content": (
                        f"You are now gathering evidence for the candidate's skills in: "
                        f"{skills_summary}. "
                        "For each skill area, ask the candidate for a concrete example from "
                        "their work. Probe gently for:\n"
                        "  • Autonomy — did they make decisions independently?\n"
                        "  • Influence — who did their work impact?\n"
                        "  • Complexity — what made the work challenging?\n"
                        "  • Knowledge — what did they learn or apply?\n"
                        "Aim for at least one specific example per skill area. "
                        "When you have gathered sufficient evidence across all skill areas "
                        "(or the candidate has exhausted their examples), "
                        "call evidence_complete."
                    ),
                }
            ],
            "functions": [
                FlowsFunctionSchema(
                    name="evidence_complete",
                    description=(
                        "Sufficient evidence has been gathered across the identified "
                        "skill areas. Transition to summary."
                    ),
                    properties={},
                    required=[],
                    handler=self.handle_evidence_complete,
                ),
            ],
        }

    def _build_summary_node(self) -> Any:
        FlowsFunctionSchema = _import_flows_schema()
        return {
            "role_message": _BOT_PERSONA,
            "task_messages": [
                {
                    "role": "user",
                    "content": (
                        "Summarise the key skills and examples of evidence you heard "
                        "during the conversation. Keep it concise (2-4 sentences). "
                        "Thank the candidate warmly for their time and engagement. "
                        "Let them know that a subject matter expert will review their "
                        "assessment and they will hear back with feedback. "
                        "Once you have delivered the summary, call summary_complete."
                    ),
                }
            ],
            "functions": [
                FlowsFunctionSchema(
                    name="summary_complete",
                    description="Summary has been delivered to the candidate. Move to closing.",
                    properties={},
                    required=[],
                    handler=self.handle_summary_complete,
                ),
            ],
        }

    def _build_closing_node(self) -> Any:
        FlowsFunctionSchema = _import_flows_schema()
        return {
            "role_message": _BOT_PERSONA,
            "task_messages": [
                {
                    "role": "user",
                    "content": (
                        "Thank the candidate warmly and say goodbye professionally. "
                        "Mention that the next step is SME review and they will receive "
                        "feedback within a few business days. "
                        "Once you have said goodbye, call call_ended to end the session."
                    ),
                }
            ],
            "functions": [
                FlowsFunctionSchema(
                    name="call_ended",
                    description="Goodbye has been said. End the call session now.",
                    properties={},
                    required=[],
                    handler=self.handle_end_call,
                ),
            ],
        }


def _try_build(builder: Any) -> Any:
    """Call ``builder()`` and return the NodeConfig, or ``None`` if pipecat-ai-flows
    is not installed (lean CI / test environment without [voice] extras).
    """
    try:
        return builder()
    except RuntimeError as exc:
        if "pipecat-ai-flows is not installed" in str(exc):
            return None
        raise


def _import_flows_schema() -> Any:
    """Lazy import of FlowsFunctionSchema from pipecat-ai-flows."""
    try:
        from pipecat_flows import FlowsFunctionSchema

        return FlowsFunctionSchema
    except ImportError as exc:
        raise RuntimeError(
            "pipecat-ai-flows is not installed. "
            "Install the voice-engine with `pip install -e .[voice]`."
        ) from exc


__all__ = ["SfiaFlowController"]
