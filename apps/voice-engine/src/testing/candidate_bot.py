"""CandidatePersona and CandidateBot — AI-powered mock interview candidate.

The candidate is a Claude instance whose behaviour is shaped by three parameters:
- role: job title / context sentence
- sfia_level: genuine capability level (1–7)
- honesty: how truthfully they represent that level (1=fabricates, 10=accurate)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_LEVEL_DESCRIPTORS = {
    1: "Follow — performs routine, supervised tasks with close guidance",
    2: "Assist — supports others, works under direction on defined tasks",
    3: "Apply — works without close supervision on routine problems",
    4: "Enable — influences small teams, manages own work across projects",
    5: "Ensure/Advise — accountable for outcomes, advises teams, sets standards",
    6: "Initiate/Influence — shapes direction, influences across the organisation",
    7: "Set Strategy — sets organisational strategy and direction at the highest level",
}

_HONESTY_INSTRUCTIONS = {
    (9, 10): (
        "Answer honestly and accurately. Your examples genuinely reflect work at "
        "your stated SFIA level. Be specific and concrete."
    ),
    (6, 8): (
        "Mostly honest, but occasionally present team achievements as primarily "
        "your own. Slightly over-state your seniority in one or two examples."
    ),
    (3, 5): (
        "Moderately exaggerate. Claim credit for work you observed or partially "
        "contributed to. Present outcomes as more impactful than they were. "
        "Avoid outright lies but stretch the truth."
    ),
    (1, 2): (
        "Heavily fabricate. Invent plausible-sounding project names and outcomes. "
        "Claim to have led initiatives that were run by others. Present yourself "
        "as operating 2–3 SFIA levels above your actual capability."
    ),
}


def _honesty_instruction(honesty: int) -> str:
    for (lo, hi), text in _HONESTY_INSTRUCTIONS.items():
        if lo <= honesty <= hi:
            return text
    return _HONESTY_INSTRUCTIONS[(9, 10)]


@dataclass
class CandidatePersona:
    role: str
    sfia_level: int
    honesty: int
    model: str = "claude-haiku-4-5-20251001"  # latest Haiku; not user-configurable

    def __post_init__(self) -> None:
        if not 1 <= self.sfia_level <= 7:
            raise ValueError(f"sfia_level must be 1–7, got {self.sfia_level}")
        if not 1 <= self.honesty <= 10:
            raise ValueError(f"honesty must be 1–10, got {self.honesty}")

    def system_prompt(self) -> str:
        level_desc = _LEVEL_DESCRIPTORS[self.sfia_level]
        honesty_inst = _honesty_instruction(self.honesty)
        return (
            f"You are Alex, a candidate in a structured skills assessment interview.\n\n"
            f"Your role: {self.role}\n"
            f"Your genuine SFIA responsibility level: {self.sfia_level} — {level_desc}\n\n"
            f"Behaviour: {honesty_inst}\n\n"
            "Keep responses conversational and natural (2–4 sentences per answer). "
            "Do NOT mention SFIA levels, SFIA codes, or framework names explicitly — "
            "talk naturally about your work. "
            "When asked for examples, provide specific but realistic work scenarios "
            "consistent with your role and level. "
            "If the interviewer asks for consent at the start, give it enthusiastically."
        )


class CandidateBot:
    """Claude-backed candidate that maintains conversation history across turns."""

    def __init__(self, persona: CandidatePersona, api_key: str) -> None:
        self._persona = persona
        self._api_key = api_key
        self._history: list[dict[str, Any]] = []
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise RuntimeError(
                    "anthropic SDK not installed. "
                    "Run: pip install -e .[voice]"
                ) from exc
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def respond(self, interviewer_message: str) -> str:
        client = self._get_client()
        self._history.append({"role": "user", "content": interviewer_message})
        response = await client.messages.create(
            model=self._persona.model,
            max_tokens=300,
            system=self._persona.system_prompt(),
            messages=self._history,
        )
        text: str = response.content[0].text
        self._history.append({"role": "assistant", "content": text})
        return text


__all__ = ["CandidateBot", "CandidatePersona"]
