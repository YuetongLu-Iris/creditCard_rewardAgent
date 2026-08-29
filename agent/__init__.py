"""
agent
-----
Package interface. `from agent import chat` stays stable for callers
(e.g. main.py) even as the harness and skills evolve underneath it.
"""
from .harness import Harness, build_default_harness, SYSTEM_PROMPT

_default_harness = build_default_harness()


def chat(
    user_message: str,
    conversation_history: list[dict],
    image: dict | None = None,
) -> tuple[str, list[dict]]:
    return _default_harness.chat(user_message, conversation_history, image=image)
