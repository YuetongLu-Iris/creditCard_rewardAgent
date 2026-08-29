"""
skills/recommend_new_card.py
-------------------------------
Recommends a new credit card worth opening, based on live web research
plus the user's actual spending pattern and the cards they already own.

Unlike the other skills, this one is not a pure local computation — it runs
its own nested Claude call with web_search enabled (via _search_agent.py) to
research current sign-up offers before answering.
"""
from pathlib import Path

from .base import Skill
from ._data import load_transactions, load_user_cards
from ._search_agent import run_search_agent
from rewards_engine import analyze_transactions

PROMPT_PATH = Path(__file__).parent / "prompts" / "recommend_new_card.md"

OUTPUT_TOOL = {
    "name": "report_recommendation",
    "description": "Report the final card recommendation(s) to the user.",
    "input_schema": {
        "type": "object",
        "properties": {
            "recommendation": {
                "type": "string",
                "description": (
                    "The full recommendation write-up in markdown: top pick(s), "
                    "why, signup bonus value, annual fee, how it compares to "
                    "cards the user already owns, and sources."
                ),
            }
        },
        "required": ["recommendation"],
    },
}


class RecommendNewCardSkill(Skill):
    name = "recommend_new_card_to_open"
    description = (
        "Searches the web for current credit card sign-up bonuses and "
        "recommends a new card worth opening, based on the user's actual "
        "spending pattern and the cards they already own. Use this when the "
        "user asks what card they should open, what's worth signing up for "
        "right now, or wants a new-card recommendation."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "focus": {
                "type": "string",
                "description": (
                    "Optional: narrow the search, e.g. 'travel', 'cashback', "
                    "'no annual fee'. Omit for a general recommendation."
                ),
            }
        },
        "required": [],
    }

    def run(self, focus: str | None = None) -> str:
        system_prompt = PROMPT_PATH.read_text()

        owned = load_user_cards()
        owned_names = [c["card_name"] for c in owned] or ["(none on file)"]

        transactions = load_transactions()
        spend_summary = "No transaction data available."
        if transactions:
            report = analyze_transactions(transactions)
            spend_summary = "\n".join(
                f"  {s.category}: ${s.total_spent:.2f}"
                for s in sorted(report["category_summaries"], key=lambda s: -s.total_spent)
            )

        user_prompt = (
            f"Cards the user already owns: {', '.join(owned_names)}\n\n"
            f"User's spending by category:\n{spend_summary}\n\n"
            f"Focus: {focus or 'general — best overall option'}\n\n"
            "Research current credit card sign-up offers and recommend the "
            "best one(s) to open, per your instructions."
        )

        result = run_search_agent(system_prompt, user_prompt, OUTPUT_TOOL)
        return result["recommendation"]
