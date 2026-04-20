"""Unit tests for the basic-call script (Phase 3 Revision 1).

These tests exercise the dataclass-level script definition — the
Pipecat runtime integration is covered by ``test_bot_runner.py``.
"""

from __future__ import annotations

from src.flows.greeting_flow import (
    BOT_CALLER_ID,
    BOT_NAME,
    GOODBYE,
    GREETING_INTRO,
    QUESTION_PROMPT,
    BasicCallScript,
    build_flow_config,
    build_script,
)


def test_bot_identity() -> None:
    assert BOT_NAME == "Noa"
    assert BOT_CALLER_ID == "Resonant · Noa"


def test_greeting_messages_cover_three_steps() -> None:
    assert GREETING_INTRO.startswith("Hi, I'm Noa calling on behalf of Resonant")
    assert "one sentence" in QUESTION_PROMPT
    assert GOODBYE.endswith("Goodbye.")


def test_build_script_injects_org_name() -> None:
    script = build_script(bot_name="Zara", org_name="AcmeCo")
    assert script.bot_name == "Zara"
    assert script.org_name == "AcmeCo"
    assert "Zara" in script.greeting
    assert "AcmeCo" in script.greeting


def test_intro_messages_in_order() -> None:
    script = build_script()
    intro = script.intro_messages()
    assert len(intro) == 2
    assert intro[0].startswith("Hi, I'm Noa")
    assert "one sentence" in intro[1]


def test_build_ack_messages_shape() -> None:
    script = build_script()
    msgs = script.build_ack_messages("I lead the platform team.")
    assert msgs[0]["role"] == "system"
    assert "one short" in msgs[0]["content"].lower()
    assert msgs[1]["role"] == "user"
    assert "I lead the platform team." in msgs[1]["content"]


def test_fallback_ack_is_safe_string() -> None:
    script = BasicCallScript()
    assert script.fallback_ack() == "Thanks for sharing that."


def test_flow_config_shape_backwards_compat() -> None:
    config = build_flow_config()
    assert config["bot_name"] == BOT_NAME
    assert config["org_name"] == "Resonant"
    assert isinstance(config["intro_messages"], list)
    assert len(config["intro_messages"]) == 2
    assert config["goodbye"] == GOODBYE
