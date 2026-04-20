"""Unit tests for the greeting flow config."""

from __future__ import annotations

from src.flows.greeting_flow import (
    BOT_CALLER_ID,
    BOT_NAME,
    GREETING_CONFIRMATION,
    GREETING_INTRO,
    GREETING_THANKS,
    build_flow_config,
)


def test_bot_identity() -> None:
    assert BOT_NAME == "Noa"
    assert BOT_CALLER_ID == "Resonant · Noa"


def test_greeting_messages_cover_three_steps() -> None:
    assert GREETING_INTRO.startswith("Hi, I'm Noa from Resonant")
    assert GREETING_CONFIRMATION == "Can you hear me clearly?"
    assert GREETING_THANKS.startswith("Thank you")


def test_flow_config_shape() -> None:
    config = build_flow_config()
    assert config["initial_node"] == "greeting"
    greeting = config["nodes"]["greeting"]
    assert greeting["post_actions"] == [{"type": "end_conversation"}]
    assert greeting["role_messages"][0]["role"] == "system"
    content = greeting["role_messages"][0]["content"]
    assert GREETING_INTRO in content
    assert GREETING_CONFIRMATION in content
    assert GREETING_THANKS in content
