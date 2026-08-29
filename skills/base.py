"""
skills/base.py
---------------
The Skill interface. Every capability the agent can call is a Skill:
it declares its own tool schema (name/description/input_schema) and
implements run() to produce a human-readable result for the LLM.

The agent harness (agent/harness.py) only ever talks to this interface —
it has no knowledge of what any specific skill does.
"""
from abc import ABC, abstractmethod


class Skill(ABC):
    name: str
    description: str
    input_schema: dict

    @abstractmethod
    def run(self, **kwargs) -> str:
        """Execute the skill and return a human-readable result for the LLM."""

    def to_tool_def(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
