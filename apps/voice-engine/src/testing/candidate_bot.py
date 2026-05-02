"""CandidatePersona and CandidateBot — AI-powered mock interview candidate.

The candidate is a Claude instance shaped by four parameters:
- role: job title / persona context
- sfia_level: genuine capability level (1–7)
- honesty: how truthfully they represent that level (1=fabricates, 10=accurate)
- target_skills: 3 SFIA codes the candidate wants to be assessed on
  (an honest candidate has real experience; a dishonest one fabricates it)
- model: which Claude model to use — proxy for candidate intelligence/articulateness
"""

from __future__ import annotations

from dataclasses import dataclass, field
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

_ARTICULATION_INSTRUCTIONS: list[tuple[range, str]] = [
    (range(1, 3), (
        "You speak very poorly. Use lots of filler words (um, uh, like, you know, sort of), "
        "trail off mid-sentence, repeat yourself, and ramble before getting to the point. "
        "Answers feel disorganised and hard to follow."
    )),
    (range(3, 5), (
        "You speak below average. Use frequent filler words (um, uh, like), occasionally "
        "lose your train of thought, and sometimes circle back to earlier points. Answers "
        "are loosely organised."
    )),
    (range(5, 7), (
        "You speak averagely. Occasional filler words (um, you know) and minor rambling, "
        "but generally get to the point within 2–3 sentences."
    )),
    (range(7, 9), (
        "You speak well. Clear and mostly concise, with only rare filler words. Answers "
        "are structured and easy to follow."
    )),
    (range(9, 11), (
        "You speak very polishedly. No filler words, perfectly structured answers, "
        "precise vocabulary. Responses feel almost rehearsed in their clarity."
    )),
]

_HONESTY_INSTRUCTIONS = {
    (9, 10): (
        "Answer honestly and accurately. Your examples genuinely reflect work at "
        "your stated SFIA level in your target skill areas. Be specific and concrete."
    ),
    (6, 8): (
        "Mostly honest, but occasionally present team achievements as primarily "
        "your own. Slightly over-state your seniority in one or two examples."
    ),
    (3, 5): (
        "Moderately exaggerate. Claim credit for work you observed or partially "
        "contributed to. Present outcomes as more impactful than they were. "
        "Avoid outright lies but stretch the truth significantly."
    ),
    (1, 2): (
        "Heavily fabricate. You have the role described but little real expertise in "
        "your target skills. Invent plausible-sounding project names and outcomes. "
        "Claim to have led initiatives that were actually run by others. Present "
        "yourself as operating 2–3 SFIA levels above your actual capability."
    ),
}

# Skill names for readable persona prompts — mirrors StubKnowledgeBase
SFIA_SKILL_NAMES: dict[str, str] = {
    "PROG": "Programming/software development",
    "DENG": "Data engineering",
    "CLOP": "Cloud operations",
    "ARCH": "Solution architecture",
    "SCTY": "Information security",
    "ITMG": "IT management",
    "PRMG": "Project management",
    "BUAN": "Business analysis",
    "TEST": "Testing",
    "DBAD": "Database administration",
    "NTAS": "Network administration",
    "HSIN": "Hardware/infrastructure",
    "SINT": "Systems integration and testing",
    "DESN": "Systems design",
    "DLMG": "Delivery management",
}

CANDIDATE_MODELS: dict[str, str] = {
    "haiku":  "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus":   "claude-opus-4-7",
}


def _honesty_instruction(honesty: int) -> str:
    for (lo, hi), text in _HONESTY_INSTRUCTIONS.items():
        if lo <= honesty <= hi:
            return text
    return _HONESTY_INSTRUCTIONS[(9, 10)]


def _articulation_instruction(articulation: int) -> str:
    for r, text in _ARTICULATION_INSTRUCTIONS:
        if articulation in r:
            return text
    return _ARTICULATION_INSTRUCTIONS[-1][1]


@dataclass
class CandidatePersona:
    role: str
    sfia_level: int
    honesty: int
    target_skills: list[str] = field(default_factory=list)
    model: str = CANDIDATE_MODELS["haiku"]
    articulation: int = 10

    def __post_init__(self) -> None:
        if not 1 <= self.sfia_level <= 7:
            raise ValueError(f"sfia_level must be 1–7, got {self.sfia_level}")
        if not 1 <= self.honesty <= 10:
            raise ValueError(f"honesty must be 1–10, got {self.honesty}")
        if not 1 <= self.articulation <= 10:
            raise ValueError(f"articulation must be 1–10, got {self.articulation}")

    def system_prompt(self) -> str:
        level_desc = _LEVEL_DESCRIPTORS[self.sfia_level]
        honesty_inst = _honesty_instruction(self.honesty)
        articulation_inst = _articulation_instruction(self.articulation)

        skills_block = ""
        if self.target_skills:
            skill_list = ", ".join(
                f"{code} ({SFIA_SKILL_NAMES.get(code, code)})"
                for code in self.target_skills
            )
            skills_block = (
                f"\n\nTarget skills: You want the assessment to cover {skill_list}. "
                "Steer the conversation naturally towards these areas when describing "
                "your background and when asked for examples. Do not mention skill "
                "codes explicitly — just talk about the work itself."
            )

        return (
            f"You are Alex, a candidate in a structured skills assessment interview.\n\n"
            f"Your role: {self.role}\n"
            f"Your genuine SFIA responsibility level: {self.sfia_level} — {level_desc}"
            f"{skills_block}\n\n"
            f"Behaviour: {honesty_inst}\n\n"
            f"Speech style: {articulation_inst}\n\n"
            "Do NOT mention SFIA levels, SFIA codes, or framework names explicitly — "
            "talk naturally about your work. "
            "When asked for examples, provide specific but realistic work scenarios. "
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
                    "anthropic SDK not installed. Run: pip install -e .[voice]"
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


__all__ = ["CANDIDATE_MODELS", "SFIA_SKILL_NAMES", "CandidateBot", "CandidatePersona"]
