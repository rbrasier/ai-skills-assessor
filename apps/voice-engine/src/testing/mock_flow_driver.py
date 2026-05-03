"""MockFlowDriver and StubKnowledgeBase.

MockFlowDriver drives SfiaFlowController through all 5 states as a text-only
conversation, without Pipecat, LiveKit, STT, or TTS.

StubKnowledgeBase provides in-memory SFIA skill definitions so the full
ClaimExtractor RAG pipeline works without a running pgvector instance.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from typing import Any

# ── Pipecat monkeypatch ───────────────────────────────────────────────────────
# Install a minimal mock of pipecat_flows if the real library is absent.
# SfiaFlowController's node builders call FlowsFunctionSchema(...); our mock
# captures the same kwargs so the node dict is fully usable by the driver.
# If the real library IS installed, it stays in sys.modules unchanged.

if "pipecat_flows" not in sys.modules:
    @dataclass
    class _MockFlowsFunctionSchema:
        name: str
        description: str
        properties: dict
        required: list
        handler: Any

    _mock_pipecat = types.ModuleType("pipecat_flows")
    _mock_pipecat.FlowsFunctionSchema = _MockFlowsFunctionSchema  # type: ignore[attr-defined]
    sys.modules["pipecat_flows"] = _mock_pipecat

# ── Imports that follow the monkeypatch ───────────────────────────────────────

import logging

from src.domain.ports.knowledge_base import IKnowledgeBase, SkillDefinition
from src.domain.services.transcript_recorder import TranscriptRecorder

logger = logging.getLogger(__name__)


def _short_model_label(model_id: str) -> str:
    if "haiku" in model_id:
        return "haiku"
    if "sonnet" in model_id:
        return "sonnet"
    if "opus" in model_id:
        return "opus"
    return model_id


class MockInterviewTimeoutError(RuntimeError):
    """Raised when max_turns is reached without the interview completing."""


# ── StubKnowledgeBase ─────────────────────────────────────────────────────────

_SFIA_STUBS: dict[str, tuple[str, str]] = {
    # code: (name, category)
    "PROG": ("Programming/software development", "Development and implementation"),
    "DENG": ("Data engineering", "Development and implementation"),
    "CLOP": ("Cloud operations", "Delivery and operation"),
    "ARCH": ("Solution architecture", "Strategy and architecture"),
    "SCTY": ("Information security", "Strategy and architecture"),
    "ITMG": ("IT management", "Management and governance"),
    "PRMG": ("Project management", "Management and governance"),
    "BUAN": ("Business analysis", "Business change"),
    "TEST": ("Testing", "Development and implementation"),
    "DBAD": ("Database administration", "Delivery and operation"),
    "NTAS": ("Network administration", "Delivery and operation"),
    "HSIN": ("Hardware/infrastructure", "Delivery and operation"),
    "SINT": ("Systems integration and testing", "Development and implementation"),
    "DESN": ("Systems design", "Development and implementation"),
    "DLMG": ("Delivery management", "Management and governance"),
}

_LEVEL_BEHAVIOUR: dict[int, str] = {
    1: "Performs routine tasks under close supervision. No decision authority.",
    2: "Assists others and works on defined tasks. Limited autonomy.",
    3: "Works without close supervision. Applies knowledge to routine problems.",
    4: "Takes ownership of tasks, influences small teams, plans own work.",
    5: "Accountable for outcomes. Advises teams, establishes standards, initiates improvements.",
    6: "Shapes organisational direction. Influences strategy across departments.",
    7: "Sets organisational strategy. Accountable at board or equivalent level.",
}


class StubKnowledgeBase(IKnowledgeBase):
    """In-memory SFIA knowledge base for mock interviews.

    Covers 15 common SFIA 9 skill codes with descriptions at all 7 levels.
    query() uses simple keyword overlap rather than vector similarity.
    """

    def _make_definitions(self, code: str) -> list[SkillDefinition]:
        name, category = _SFIA_STUBS[code]
        return [
            SkillDefinition(
                skill_code=code,
                skill_name=name,
                category=category,
                subcategory=None,
                level=lvl,
                content=(
                    f"{name} — Level {lvl}: {behaviour} "
                    f"Applied to {name.lower()} work."
                ),
                similarity=None,
                framework_type="sfia-9",
            )
            for lvl, behaviour in _LEVEL_BEHAVIOUR.items()
        ]

    async def query(
        self,
        text: str,
        framework_type: str = "sfia-9",
        top_k: int = 5,
        level_filter: int | None = None,
        skill_codes: list[str] | None = None,
    ) -> list[SkillDefinition]:
        words = set(text.lower().split())
        scored: list[tuple[int, SkillDefinition]] = []
        codes = skill_codes or list(_SFIA_STUBS.keys())
        for code in codes:
            if code not in _SFIA_STUBS:
                continue
            for defn in self._make_definitions(code):
                if level_filter is not None and defn.level != level_filter:
                    continue
                overlap = len(words & set(defn.content.lower().split()))
                scored.append((overlap, defn))
        scored.sort(key=lambda x: -x[0])
        return [d for _, d in scored[:top_k]]

    async def query_by_skill_code(
        self,
        skill_code: str,
        framework_type: str = "sfia-9",
    ) -> list[SkillDefinition]:
        if skill_code not in _SFIA_STUBS:
            return []
        return self._make_definitions(skill_code)


# ── Tool conversion helpers ───────────────────────────────────────────────────

def _node_func_to_tool(func: Any) -> dict[str, Any]:
    """Convert a FlowsFunctionSchema (real or mock) to an Anthropic tool dict."""
    return {
        "name": func.name,
        "description": func.description,
        "input_schema": {
            "type": "object",
            "properties": func.properties or {},
            "required": func.required or [],
        },
    }


def _find_func(functions: list[Any], name: str) -> Any | None:
    return next((f for f in functions if f.name == name), None)


# ── MockFlowDriver ────────────────────────────────────────────────────────────

class MockFlowDriver:
    """Drives SfiaFlowController as a text conversation without Pipecat.

    Uses two Claude instances:
    - Noa (interviewer): driven by SfiaFlowController node configs.
    - Candidate: driven by CandidateBot.
    """

    def __init__(
        self,
        noa_model: str,
        candidate_bot: Any,
        api_key: str,
        max_turns: int = 40,
        print_dialog: bool = False,
    ) -> None:
        self._noa_model = noa_model
        self._candidate_bot = candidate_bot
        self._api_key = api_key
        self._max_turns = max_turns
        self._print_dialog = print_dialog
        self._noa_client: Any = None

    def _get_noa_client(self) -> Any:
        if self._noa_client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise RuntimeError("anthropic SDK not installed.") from exc
            self._noa_client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._noa_client

    async def run(
        self,
        controller: Any,
        recorder: TranscriptRecorder,
        *,
        persistence: Any = None,
        session_id: str = "",
    ) -> None:
        """Drive the full interview from Introduction to Closing.

        When ``persistence`` and ``session_id`` are supplied, each turn is
        written to storage via ``save_transcript_turn`` as it occurs —
        mirroring the progressive transcript saving a live call produces.
        """
        client = self._get_noa_client()
        current_node = controller.get_initial_node()
        messages: list[dict[str, Any]] = list(current_node.get("task_messages", []))
        tools = [_node_func_to_tool(f) for f in current_node["functions"]]
        done = False
        turn = 0

        while not done:
            if turn >= self._max_turns:
                raise MockInterviewTimeoutError(
                    f"Mock interview exceeded {self._max_turns} turns without completing. "
                    "Increase --max-turns or check the flow controller configuration."
                )
            turn += 1

            response = await client.messages.create(
                model=self._noa_model,
                system=current_node["role_message"],
                messages=messages,
                tools=tools,
                max_tokens=600,
            )

            text_blocks = [b for b in response.content if b.type == "text"]
            tool_uses = [b for b in response.content if b.type == "tool_use"]

            # Record any text Noa produced this turn
            noa_text = " ".join(b.text.strip() for b in text_blocks if b.text.strip())
            if noa_text:
                recorder.record_turn(speaker="bot", text=noa_text)
                if persistence and session_id and recorder.turn_count > 0:
                    await persistence.save_transcript_turn(
                        session_id, recorder.to_dict()["turns"][-1]
                    )
                if self._print_dialog:
                    print(f"  Noa ({_short_model_label(self._noa_model)}): {noa_text}")

            if tool_uses:
                # Add full assistant response (text + tool_use blocks)
                messages.append({"role": "assistant", "content": list(response.content)})

                tool_results: list[dict[str, Any]] = []
                new_node: Any = None

                for tb in tool_uses:
                    func = _find_func(current_node["functions"], tb.name)
                    if func is None:
                        logger.warning("MockFlowDriver: unknown function %s — skipping", tb.name)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tb.id,
                            "content": "Unknown function.",
                        })
                        continue

                    _, returned_node = await func.handler(tb.input or {}, None)

                    if tb.name == "call_ended":
                        done = True
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tb.id,
                            "content": "Session ended.",
                        })
                        break

                    if returned_node is not None:
                        new_node = returned_node

                    # Embed next node's task instruction in the tool result to
                    # avoid back-to-back user messages (Anthropic API constraint).
                    next_task = ""
                    if new_node and new_node.get("task_messages"):
                        next_task = "\n\n" + new_node["task_messages"][0]["content"]

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tb.id,
                        "content": f"OK.{next_task}",
                    })

                messages.append({"role": "user", "content": tool_results})

                if new_node is not None:
                    current_node = new_node
                    tools = [_node_func_to_tool(f) for f in current_node["functions"]]

            else:
                # Pure text turn — get candidate response
                if not noa_text:
                    logger.debug("MockFlowDriver: empty Noa turn %d — skipping candidate", turn)
                    continue

                messages.append({"role": "assistant", "content": noa_text})
                candidate_text = await self._candidate_bot.respond(noa_text)
                recorder.record_turn(speaker="candidate", text=candidate_text)
                if persistence and session_id and recorder.turn_count > 0:
                    await persistence.save_transcript_turn(
                        session_id, recorder.to_dict()["turns"][-1]
                    )
                if self._print_dialog:
                    candidate_label = _short_model_label(self._candidate_bot._persona.model)
                    print(f"  Candidate ({candidate_label}): {candidate_text}")
                messages.append({"role": "user", "content": candidate_text})

        logger.info("MockFlowDriver: interview complete in %d turns", turn)


__all__ = ["MockFlowDriver", "MockInterviewTimeoutError", "StubKnowledgeBase"]
