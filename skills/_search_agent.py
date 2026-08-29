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
# max_uses caps explicit web_search calls, but the tool's built-in dynamic
# filtering can still spend a lot of the turn on internal code_execution
# rounds before responding — keep this tight so a broad, open-ended query
# doesn't spiral into a multi-minute single turn.
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 3}


def run_search_agent(system_prompt: str, user_prompt: str, output_tool: dict, max_turns: int = 4) -> dict:
    """
    Runs a nested Claude loop with web_search enabled until Claude calls
    `output_tool` (a standard tool_def dict) with a clean (non-truncated)
    stop. Returns that call's `input`.

    web_search is a server-side tool — Anthropic executes it and attaches
    results inline, so no client-side tool_result handling is needed for it.
    """
    messages = [{"role": "user", "content": user_prompt}]
    tools = [WEB_SEARCH_TOOL, output_tool]

    for _ in range(max_turns):
        response = client.messages.create(
            model=MODEL,
            # Generous: a single turn can involve several search + internal
            # code_execution rounds before Claude is ready to answer. Too
            # low a budget truncates the final tool call mid-arguments
            # instead of just running short on research.
            max_tokens=8000,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            for block in response.content:
                if block.type == "tool_use" and block.name == output_tool["name"]:
                    return block.input

        if response.stop_reason == "max_tokens":
            # The turn got cut off mid-flight — any tool_use block present
            # is likely truncated/incomplete, so don't trust it. Nudge
            # toward a decisive answer rather than more research.
            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": (
                    f"You're running long. Stop researching and call "
                    f"{output_tool['name']} now with your best answer so far."
                ),
            })
            continue

        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": f"Call the {output_tool['name']} tool now with your findings.",
        })

    raise RuntimeError(f"Search agent did not produce a result within {max_turns} turns.")
