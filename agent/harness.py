"""
agent/harness.py
------------------
The agent loop: sends messages to Claude's tool-calling API, executes
whichever skill Claude decides to call, feeds results back, and repeats
until Claude produces a final text response.

This module knows nothing about what any specific skill does — it only
talks to the Skill interface (skills/base.py). Add a new skill by
registering it in skills/__init__.py; this file never needs to change.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
import anthropic

from skills.base import Skill

MODEL = "claude-sonnet-4-6"

IMAGE_GUIDANCE_PATH = Path(__file__).parent.parent / "skills" / "prompts" / "image_understanding.md"

SYSTEM_PROMPT = """You are a helpful credit card rewards optimization assistant.
You have access to the user's real spending data and a database of credit card
rewards rates. Your job is to help users maximize their cashback and points by
recommending the right card for each purchase and identifying missed rewards.

Always use the available tools to fetch real data before answering — never guess
or make up numbers.

Keep responses SHORT by default — 1-3 sentences for a quick card recommendation.
State the card and the one key reason, skip preambles ("Great question!"), skip
markdown tables and full multi-card breakdowns unless the user actually asks to
compare cards or for more detail. The product's core value is speed: someone
should be able to send a photo of a receipt and immediately see which card to
use, nothing more, unless they ask a follow-up.

The app separately asks the user (via its own UI, not you) which card they
actually used after a recommendation — don't ask "let me know which card you
used" yourself, that's already handled.

The user's owned-cards list lives in their browser, not on the server — when
a message includes a "[Context: the user currently owns...]" note, that's
the current list for this turn. When calling recommend_new_card_to_open or
remove_owned_card, pass that list along via their owned_cards parameter so
they have it too (their own memory doesn't persist it across turns).

""" + IMAGE_GUIDANCE_PATH.read_text()


class Harness:
    """Runs the Claude tool-calling loop over a set of Skills."""

    def __init__(self, skills: list[Skill], system_prompt: str = SYSTEM_PROMPT, model: str = MODEL):
        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from environment
        self.skills_by_name = {s.name: s for s in skills}
        self.tools = [s.to_tool_def() for s in skills]
        self.system_prompt = system_prompt
        self.model = model

    def run_tool(self, tool_name: str, tool_input: dict) -> str:
        """Route a tool call from Claude to the matching skill."""
        skill = self.skills_by_name.get(tool_name)
        if skill is None:
            return f"Unknown tool: {tool_name}"
        return skill.run(**tool_input)

    def chat(
        self,
        user_message: str,
        conversation_history: list[dict],
        image: dict | None = None,
        owned_cards: list[str] | None = None,
    ) -> tuple[str, list[dict], list[dict]]:
        """
        Send a message to the agent and return its response.
        Handles multi-step tool calling automatically.

        image, if given, is {"media_type": "image/jpeg", "data": <base64 str>} —
        e.g. a photo of a receipt or storefront. Claude reads it natively as
        part of this turn (see skills/prompts/image_understanding.md for how
        it's expected to act on what it sees).

        owned_cards, if given, is the user's current owned-card names (the
        frontend's source of truth, not the server's) — injected as context
        so recommendations can account for it.

        Returns (response_text, updated_history, tool_calls) — tool_calls is
        [{"name": ..., "input": ...}] for every tool Claude invoked this turn,
        so callers (e.g. the /chat endpoint) can react deterministically to
        what happened without having to parse the response text.
        """
        tool_calls: list[dict] = []
        content_blocks = []
        if owned_cards:
            content_blocks.append({
                "type": "text",
                "text": f"[Context: the user currently owns these cards: {', '.join(owned_cards)}]",
            })
        if image:
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image["media_type"],
                    "data": image["data"],
                },
            })
        if user_message:
            content_blocks.append({"type": "text", "text": user_message})

        conversation_history.append({"role": "user", "content": content_blocks})

        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self.system_prompt,
                tools=self.tools,
                messages=conversation_history,
            )

            if response.stop_reason == "tool_use":
                conversation_history.append({
                    "role": "assistant",
                    "content": response.content,
                })

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        print(f"  🔧 Calling tool: {block.name}({block.input})")
                        tool_calls.append({"name": block.name, "input": block.input})
                        result = self.run_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                conversation_history.append({
                    "role": "user",
                    "content": tool_results,
                })
                # Loop again so Claude can formulate its final response

            else:
                response_text = next(
                    (block.text for block in response.content if hasattr(block, "text")),
                    "I couldn't generate a response.",
                )
                conversation_history.append({
                    "role": "assistant",
                    "content": response_text,
                })
                return response_text, conversation_history, tool_calls


def build_default_harness() -> Harness:
    from skills import ALL_SKILLS
    return Harness(ALL_SKILLS)
