"""Basic-call script (Phase 3 Revision 1).

Defines the minimum viable conversation the bot runs end-to-end:

  1. TTS: greeting.
  2. TTS: one question.
  3. Wait for the candidate's reply (STT).
  4. LLM: a single one-shot acknowledgement based on the reply.
  5. TTS: goodbye.
  6. Hangup.

No SFIA, no skill mapping, no interjections — those live in Phase 4.

The module is carefully import-safe: it never imports Pipecat at module
level so the lean CI image (which doesn't install the ``[voice]``
extras) can still load it. Pipecat is imported lazily inside the
helpers that actually need it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BOT_NAME = "Noa"
BOT_CALLER_ID = "Resonant · Noa"

GREETING_INTRO = (
    f"Hi, I'm {BOT_NAME} calling on behalf of Resonant about your "
    "skills assessment."
)
QUESTION_PROMPT = (
    "In one sentence, what's your current role and what do you "
    "spend most of your time on day to day?"
)
GOODBYE = (
    "Thanks, that's all we need for today. We'll be in touch with "
    "next steps. Goodbye."
)

# Kept for backward-compat with Phase 2 tests that imported these.
GREETING_CONFIRMATION = GREETING_INTRO
GREETING_THANKS = GOODBYE
STUB_RESPONSES: dict[str, str] = {
    "intro": GREETING_INTRO,
    "question": QUESTION_PROMPT,
    "goodbye": GOODBYE,
}


@dataclass
class BasicCallScript:
    """The bot's deterministic dialogue plan for a single call.

    Pipecat's :class:`BasicCallBot` reads this to drive the
    conversation. Keeping it a plain dataclass means it is trivially
    unit-testable without importing Pipecat.
    """

    bot_name: str = BOT_NAME
    org_name: str = "Resonant"
    greeting: str = GREETING_INTRO
    question: str = QUESTION_PROMPT
    goodbye: str = GOODBYE
    ack_system_prompt: str = field(
        default_factory=lambda: (
            f"You are {BOT_NAME}, a warm AI phone interviewer. The candidate "
            "has just answered your first question. Reply with ONE short, "
            "natural, acknowledging sentence (max 20 words). Do not ask a "
            "follow-up question, do not summarise, do not use lists. Keep "
            "it conversational — your reply will be spoken aloud."
        )
    )

    def intro_messages(self) -> list[str]:
        """Messages the bot speaks before listening for the candidate.

        Emitted in order. The bot speaks each one, then transitions
        into listening mode for the reply.
        """
        return [self.greeting, self.question]

    def build_ack_messages(self, candidate_reply: str) -> list[dict[str, str]]:
        """System + user prompt to feed :meth:`ILLMProvider.complete`."""
        return [
            {"role": "system", "content": self.ack_system_prompt},
            {
                "role": "user",
                "content": (
                    f"The candidate replied: \"{candidate_reply.strip()}\"\n\n"
                    "Acknowledge them in one short sentence."
                ),
            },
        ]

    def fallback_ack(self) -> str:
        """Safe acknowledgement when the LLM call fails or is skipped."""
        return "Thanks for sharing that."


def build_script(
    bot_name: str = BOT_NAME,
    org_name: str = "Resonant",
) -> BasicCallScript:
    return BasicCallScript(
        bot_name=bot_name,
        org_name=org_name,
        greeting=(
            f"Hi, I'm {bot_name} calling on behalf of {org_name} about your "
            "skills assessment."
        ),
    )


# Backwards compatibility: Phase 2 tests import ``build_flow_config``.
def build_flow_config(
    bot_name: str = BOT_NAME,
    org_name: str = "Resonant",
) -> dict[str, object]:
    """Return a plain dict describing the basic-call script.

    Kept so the Phase 2 unit tests (``test_greeting_flow.py``) continue
    to work. Downstream code should prefer :func:`build_script`.
    """
    script = build_script(bot_name=bot_name, org_name=org_name)
    return {
        "bot_name": script.bot_name,
        "org_name": script.org_name,
        "intro_messages": script.intro_messages(),
        "goodbye": script.goodbye,
    }


__all__ = [
    "BOT_CALLER_ID",
    "BOT_NAME",
    "GOODBYE",
    "GREETING_CONFIRMATION",
    "GREETING_INTRO",
    "GREETING_THANKS",
    "QUESTION_PROMPT",
    "STUB_RESPONSES",
    "BasicCallScript",
    "build_flow_config",
    "build_script",
]
