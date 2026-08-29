"""
skills/remove_owned_card.py
-------------------------------
Removes a card from the user's owned-cards list — e.g. to correct a mistake
made by add_owned_card, or because the user closed the card.
"""
from .base import Skill
from ._data import load_user_cards, save_user_cards


class RemoveOwnedCardSkill(Skill):
    name = "remove_owned_card"
    description = (
        "Removes a card from the user's list of owned cards. Use this when "
        "the user says a card was added by mistake, or that they closed or "
        "no longer have a card."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "card_name": {
                "type": "string",
                "description": "The card name (or partial name) to remove.",
            }
        },
        "required": ["card_name"],
    }

    def run(self, card_name: str) -> str:
        owned = load_user_cards()
        query = card_name.lower()
        matched = [c for c in owned if query in c["card_name"].lower()]

        if not matched:
            current = ", ".join(c["card_name"] for c in owned) or "(none on file)"
            return f"No matching card found. Cards on file: {current}"

        remaining = [c for c in owned if c not in matched]
        save_user_cards(remaining)
        removed_names = ", ".join(c["card_name"] for c in matched)
        return f"Removed: {removed_names}"
