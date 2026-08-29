"""
skills/_search_agent.py
--------------------------
Shared engine for skills that need Claude to research something on the web
and hand back a structured result. Declares Anthropic's server-side
web_search tool plus a caller-supplied "output tool", runs a nested
agentic loop until Claude calls the output tool, and returns its input.

Not a skill itself — skills that need live web research call run_search_agent().
"""
import anthropic

client = anthropic.Anthropic()

MODEL = "claude-sonnet-4-6"
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}


def run_search_agent(system_prompt: str, user_prompt: str, output_tool: dict, max_turns: int = 6) -> dict:
    """
    Runs a nested Claude loop with web_search enabled until Claude calls
    `output_tool` (a standard tool_def dict). Returns that call's `input`.

    web_search is a server-side tool — Anthropic executes it and attaches
    results inline, so no client-side tool_result handling is needed for it.
    """
    messages = [{"role": "user", "content": user_prompt}]
    tools = [WEB_SEARCH_TOOL, output_tool]

    for _ in range(max_turns):
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == output_tool["name"]:
                return block.input

        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": f"Call the {output_tool['name']} tool now with your findings.",
        })

    raise RuntimeError(f"Search agent did not produce a result within {max_turns} turns.")
