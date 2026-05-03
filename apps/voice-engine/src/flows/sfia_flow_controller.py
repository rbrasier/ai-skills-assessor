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
* **RAG injection at state-transition** — ``handle_skills_identified()`` queries
  ``IKnowledgeBase`` once and stores the formatted context; the evidence
  gathering node builder embeds it in ``task_messages``. No per-turn queries.
* **Static system prompt** — injected at construction time (pre-built by
  ``SystemPromptBuilder``); replaces the old hardcoded ``_BOT_PERSONA`` constant.

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

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from src.domain.ports.knowledge_base import IKnowledgeBase, SkillDefinition
from src.domain.services.transcript_recorder import TranscriptRecorder

if TYPE_CHECKING:
    from src.domain.services.post_call_pipeline import PostCallPipeline

logger = logging.getLogger(__name__)

# Fallback persona used when SystemPromptBuilder fails to fetch framework data
# (e.g. frameworks table not yet seeded). Keeps the bot functional.
_FALLBACK_SYSTEM_PROMPT = (
    "You are Noa, a warm and professional AI skills assessor from Resonant. "
    "You conduct structured SFIA-based skills assessments over the phone. "
    "Keep your language conversational, concise, and encouraging. "
    "Never mention SFIA skill codes or numerical levels to the candidate — "
    "keep the conversation natural. "
    "When you have enough information to call a transition function, do so promptly.\n\n"
    "## Technical Challenge\n\n"
    "Occasionally — but not on every turn — introduce polite technical tension by "
    "challenging a decision the candidate has described. For example: "
    "'Why PostgreSQL rather than a graph database for that use case?' or "
    "'Some teams go serverless for that kind of workload — what was your reasoning for "
    "keeping it on VMs?'. "
    "Scale the depth and frequency of these challenges to the complexity the candidate "
    "demonstrates: light probing for routine work, sharper scrutiny when the candidate "
    "is describing architecture, strategy, or cross-team influence. "
    "The goal is to probe reasoning, not to intimidate."
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
        system_prompt: str,
        knowledge_base: IKnowledgeBase,
        framework_type: str = "sfia-9",
        session_id: str = "",
        post_call_pipeline: PostCallPipeline | None = None,
    ) -> None:
        self._recorder = recorder
        self._on_call_ended = on_call_ended
        self._system_prompt = system_prompt
        self._knowledge_base = knowledge_base
        self._framework_type = framework_type
        self._session_id = session_id
        self._post_call_pipeline = post_call_pipeline
        self._identified_skills: list[dict[str, Any]] = []
        self._rag_context: str = ""

    @property
    def identified_skills(self) -> list[dict[str, Any]]:
        return list(self._identified_skills)

    # ─── Public handlers (testable without Pipecat) ──────────────────

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
        """Skills extracted from SkillDiscovery — query RAG, then transition."""
        skills = args.get("skills", [])
        self._identified_skills = skills
        skill_codes = [s["skill_code"] for s in skills if "skill_code" in s]

        try:
            results: list[SkillDefinition] = []
            for code in skill_codes:
                definitions = await self._knowledge_base.query_by_skill_code(
                    skill_code=code,
                    framework_type=self._framework_type,
                )
                results.extend(definitions)
            self._rag_context = _format_rag_context(results) if results else ""
        except Exception:
            logger.exception("SfiaFlow: RAG query failed — proceeding without context")
            self._rag_context = ""

        logger.info(
            "SfiaFlow: skills_identified (%d) → evidence_gathering (rag=%d chars)",
            len(skills),
            len(self._rag_context),
        )
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
        """Call complete — trigger transcript finalisation and pipeline teardown.

        _on_call_ended() → SFIACallBot._finalize_and_end() → recorder.finalize()
        guarantees the transcript is persisted before the background pipeline reads it.
        """
        logger.info("SfiaFlow: call_ended — finalising session %s", self._session_id)
        try:
            result = self._on_call_ended()
            if isinstance(result, Awaitable):
                await result
        except Exception:
            logger.exception("SfiaFlow: on_call_ended callback raised")

        if self._post_call_pipeline and self._session_id:
            asyncio.create_task(
                self._run_pipeline_safe(self._session_id),
                name=f"post-call-pipeline-{self._session_id}",
            )

        return None, None

    async def _run_pipeline_safe(self, session_id: str) -> None:
        """Run PostCallPipeline, logging errors without crashing call teardown."""
        try:
            await self._post_call_pipeline.process(session_id)  # type: ignore[union-attr]
        except Exception:
            logger.exception(
                "PostCallPipeline failed for session %s — "
                "manual re-trigger via POST /api/v1/assessment/%s/process",
                session_id,
                session_id,
            )

    # ─── Entry point ─────────────────────────────────────────────────

    def get_initial_node(self) -> Any:
        """Return the Introduction ``NodeConfig`` to seed ``FlowManager.initialize``."""
        return self._build_introduction_node()

    # ─── Node builders (require pipecat-ai-flows [voice] extras) ─────

    def _build_introduction_node(self) -> Any:
        FlowsFunctionSchema = _import_flows_schema()
        return {
            "role_message": self._system_prompt,
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
            "role_message": self._system_prompt,
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

        rag_block = (
            f"\n\n>>> SKILL DEFINITIONS START\n{self._rag_context}\n>>> SKILL DEFINITIONS END"
            if self._rag_context
            else ""
        )

        return {
            "role_message": self._system_prompt,
            "task_messages": [
                {
                    "role": "user",
                    "content": (
                        f"You are now gathering evidence for the candidate's skills in: "
                        f"{skills_summary}."
                        f"{rag_block}\n\n"
                        "Use the skill definitions above (if present) to ask "
                        "level-appropriate probing questions. For each skill, ask for "
                        "a concrete work example. Probe for: Autonomy, Influence, "
                        "Complexity, Knowledge.\n\n"
                        "Occasionally — not every turn — introduce polite technical "
                        "tension by challenging a technology or design choice the "
                        "candidate mentions. For example: 'Why that approach rather than "
                        "X?' or 'What made you rule out Y?'. Increase the sharpness of "
                        "these challenges as the candidate demonstrates higher-level "
                        "thinking (architecture, strategy, cross-team influence).\n\n"
                        "Weave in depth-probing questions that test genuine understanding, "
                        "not just familiarity. These should be specific and technical: "
                        "algorithmic questions (e.g. 'Walk me through the time complexity "
                        "of that approach'), language-specific probing (e.g. 'How does "
                        "Python's GIL affect that concurrency design?'), or design "
                        "trade-off questions (e.g. 'What would break first under load in "
                        "that architecture?'). Calibrate depth to what the candidate "
                        "claims — sharper for senior claims, gentler for junior ones. "
                        "These questions reveal whether claims are genuine or rehearsed.\n\n"
                        "When sufficient evidence is gathered across all skill areas, "
                        "call evidence_complete.\n\n"
                        "If the interview cannot continue — for example, the candidate "
                        "is clearly fabricating and has been confronted, is uncooperative, "
                        "or the conversation has broken down irreparably — call "
                        "call_ended immediately to end the session."
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
                FlowsFunctionSchema(
                    name="call_ended",
                    description=(
                        "Emergency exit: the interview cannot continue. Use when the "
                        "candidate is clearly fabricating and has been confronted, is "
                        "uncooperative, abusive, or the conversation has broken down "
                        "irreparably. End the session immediately."
                    ),
                    properties={},
                    required=[],
                    handler=self.handle_end_call,
                ),
            ],
        }

    def _build_summary_node(self) -> Any:
        FlowsFunctionSchema = _import_flows_schema()
        return {
            "role_message": self._system_prompt,
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
            "role_message": self._system_prompt,
            "task_messages": [
                {
                    "role": "user",
                    "content": (
                        "Deliver a single warm goodbye to the candidate. Mention that "
                        "the next step is SME review and they will receive feedback "
                        "within a few business days. "
                        "Immediately after your goodbye message — on that same turn or "
                        "the very next one — call call_ended. "
                        "Do NOT continue the conversation. If the candidate says anything "
                        "further, call call_ended without responding to them."
                    ),
                }
            ],
            "functions": [
                FlowsFunctionSchema(
                    name="call_ended",
                    description=(
                        "End the call session now. Call this immediately after delivering "
                        "the goodbye — do not wait for the candidate to respond."
                    ),
                    properties={},
                    required=[],
                    handler=self.handle_end_call,
                ),
            ],
        }


def _format_rag_context(results: list[SkillDefinition]) -> str:
    lines = []
    for skill in results:
        level_str = f" — Level {skill.level}" if skill.level is not None else ""
        lines.append(f"\n**{skill.skill_name} ({skill.skill_code}){level_str}**")
        lines.append(skill.content)
    return "\n".join(lines)


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
