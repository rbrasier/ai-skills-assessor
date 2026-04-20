"""Minimal Pipecat Flows greeting state machine — Phase 2.

The Phase 2 scope only requires the bot to (1) introduce itself,
(2) confirm two-way audio, (3) thank the candidate, and (4) end the
call. The config below is consumed by the Pipecat Flows runtime when
Phase 3 wires it up; in Phase 2 we expose it purely for unit-test
assertions.

Design reference: ``phase-2-basic-voice-engine.md`` §1.3.
"""

from __future__ import annotations

from typing import Any

BOT_NAME = "Noa"
BOT_CALLER_ID = "Resonant · Noa"

GREETING_INTRO = (
    f"Hi, I'm {BOT_NAME} from Resonant. "
    "I'm here to conduct a brief skills assessment interview."
)
GREETING_CONFIRMATION = "Can you hear me clearly?"
GREETING_THANKS = "Thank you for taking the time to do this assessment."


STUB_RESPONSES: dict[str, str] = {
    "intro": GREETING_INTRO,
    "confirm": GREETING_CONFIRMATION,
    "thanks": GREETING_THANKS,
}


def build_flow_config() -> dict[str, Any]:
    """Return the Pipecat Flows config dict for the Phase 2 greeting.

    Kept as a function (rather than a module-level constant) so tests
    can assert on the shape without importing Pipecat.
    """

    system_prompt = (
        f"You are {BOT_NAME}, an AI assessment interviewer from Resonant. "
        "Your job is to: "
        f"1. Introduce yourself: '{GREETING_INTRO}' "
        f"2. Ask a simple confirmation question: '{GREETING_CONFIRMATION}' "
        f"3. Thank them: '{GREETING_THANKS}' "
        "4. End the call gracefully."
    )

    return {
        "initial_node": "greeting",
        "nodes": {
            "greeting": {
                "role_messages": [
                    {"role": "system", "content": system_prompt},
                ],
                "post_actions": [{"type": "end_conversation"}],
            },
        },
    }


__all__ = [
    "BOT_CALLER_ID",
    "BOT_NAME",
    "GREETING_CONFIRMATION",
    "GREETING_INTRO",
    "GREETING_THANKS",
    "STUB_RESPONSES",
    "build_flow_config",
]
