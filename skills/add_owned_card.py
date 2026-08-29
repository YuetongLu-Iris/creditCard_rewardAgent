"""
skills/add_owned_card.py
---------------------------
Resolves a card the user says they own against the shared catalog — a
cheap local match first, or a web search (which also adds a new catalog
entry) if it's not already known. The owned-cards *list* itself lives in
the browser (localStorage), not on the server — this skill only handles
the "which card is this, and what does it earn" research; main.py reads
the resolved catalog entry back out to tell the frontend what to store.
"""
from datetime import date
from pathlib import Path

from .base import Skill
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
            "official_url": {
                "type": "string",
                "description": "URL of the issuer's official page for this card (product/rewards details).",
            },
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
        "required": ["name", "base_rate", "annual_fee", "description", "official_url", "rates"],
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
                official_url=result["official_url"],
                source="web_search",
                last_updated=date.today().isoformat(),
            )
            CARDS.append(card)
            save_cards_catalog(CARDS)

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
