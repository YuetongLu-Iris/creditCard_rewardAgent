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
or make up numbers. Be concise, friendly, and specific with dollar amounts.

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
    ) -> tuple[str, list[dict]]:
        """
        Send a message to the agent and return its response.
        Handles multi-step tool calling automatically.

        image, if given, is {"media_type": "image/jpeg", "data": <base64 str>} —
        e.g. a photo of a receipt or storefront. Claude reads it natively as
        part of this turn (see skills/prompts/image_understanding.md for how
        it's expected to act on what it sees).

        Returns (response_text, updated_history)
        """
        if image:
            content = [{
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image["media_type"],
                    "data": image["data"],
                },
            }]
            if user_message:
                content.append({"type": "text", "text": user_message})
            conversation_history.append({"role": "user", "content": content})
        else:
            conversation_history.append({"role": "user", "content": user_message})

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
                return response_text, conversation_history


def build_default_harness() -> Harness:
    from skills import ALL_SKILLS
    return Harness(ALL_SKILLS)
