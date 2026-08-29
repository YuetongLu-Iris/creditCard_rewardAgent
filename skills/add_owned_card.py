"""
skills/add_owned_card.py
---------------------------
Adds a card to the user's owned-cards list. Tries a local catalog match
first (cheap, no search needed); if the card isn't in cards_catalog.json
yet, researches it via web search and adds a new catalog entry.
"""
from datetime import date
from pathlib import Path

from .base import Skill
from ._data import load_user_cards, save_user_cards
from ._search_agent import run_search_agent
from rewards_engine import CARDS, CreditCard, RewardsRate, save_cards_catalog

PROMPT_PATH = Path(__file__).parent / "prompts" / "add_owned_card.md"

OUTPUT_TOOL = {
    "name": "report_card_details",
    "description": "Report the identified card's official name and current reward structure.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Official, full card name."},
            "base_rate": {
                "type": "number",
                "description": "Base rewards rate (e.g. 1.0 for 1x/1%) on non-bonused spend.",
            },
            "annual_fee": {"type": "number", "description": "Annual fee in dollars."},
            "description": {"type": "string", "description": "One-sentence summary of the card."},
            "rates": {
                "type": "array",
                "description": "Bonus category rates.",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Plaid-style category, e.g. 'Food and Drink', 'Travel', 'Shops'.",
                        },
                        "multiplier": {"type": "number"},
                        "description": {"type": "string"},
                    },
                    "required": ["category", "multiplier", "description"],
                },
            },
        },
        "required": ["name", "base_rate", "annual_fee", "description", "rates"],
    },
}


def _find_in_catalog(query: str) -> CreditCard | None:
    query = query.lower()
    for card in CARDS:
        if query in card.name.lower() or card.name.lower() in query:
            return card
    return None


class AddOwnedCardSkill(Skill):
    name = "add_owned_card"
    description = (
        "Adds a credit card to the user's list of cards they currently own — "
        "use this when the user says they have or just opened a specific "
        "card, even if they use an abbreviation or nickname (e.g. 'CSP', "
        "'Amex Gold'). Resolves the card against the known catalog, or "
        "researches it on the web if it's not already known, then reports "
        "back what was added so the user can correct it if it's wrong."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "card_name": {
                "type": "string",
                "description": "The card name or abbreviation as the user said it.",
            }
        },
        "required": ["card_name"],
    }

    def run(self, card_name: str) -> str:
        card = _find_in_catalog(card_name)

        if card is None:
            system_prompt = PROMPT_PATH.read_text()
            user_prompt = (
                f"The user said they have a card called '{card_name}'. "
                "Identify the exact official card and its current reward "
                "structure, then report it."
            )
            result = run_search_agent(system_prompt, user_prompt, OUTPUT_TOOL)
            card = CreditCard(
                name=result["name"],
                base_rate=result["base_rate"],
                rates=[RewardsRate(**r) for r in result["rates"]],
                annual_fee=result["annual_fee"],
                description=result["description"],
                source="web_search",
                last_updated=date.today().isoformat(),
            )
            CARDS.append(card)
            save_cards_catalog(CARDS)

        owned = load_user_cards()
        if any(c["card_name"] == card.name for c in owned):
            return f"You already have {card.name} on file — nothing to add."

        owned.append({"card_name": card.name, "added_date": date.today().isoformat()})
        save_user_cards(owned)

        rate_lines = "\n".join(
            f"  {r.category}: {r.multiplier}x ({r.description})" for r in card.rates
        )
        return (
            f"Added {card.name} to your cards.\n"
            f"  Annual fee: ${card.annual_fee:.0f}\n"
            f"  Base rate: {card.base_rate}x\n"
            f"{rate_lines}\n\n"
            "Let me know if I got the wrong card and I'll remove it."
        )
