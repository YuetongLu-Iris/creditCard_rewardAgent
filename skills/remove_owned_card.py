"""
skills/remove_owned_card.py
-------------------------------
Confirms removing a card from the user's owned-cards list — e.g. to correct
a mistake made by add_owned_card, or because the user closed the card. The
owned-cards list itself lives in the browser (localStorage); this skill
just resolves *which* card the user means from what it can see in context,
so it can echo back a clear confirmation. The frontend does the actual
removal (fuzzy-matched against its own local list) via main.py's
wallet_action signal.
"""
from .base import Skill


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
            },
            "owned_cards": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "The user's currently owned cards, as given earlier in "
                    "this conversation — pass them along so a sensible "
                    "confirmation can be given even if the name is a partial "
                    "match."
                ),
            },
        },
        "required": ["card_name"],
    }

    def run(self, card_name: str, owned_cards: list[str] | None = None) -> str:
        owned_cards = owned_cards or []
        query = card_name.lower()
        matched = [c for c in owned_cards if query in c.lower() or c.lower() in query]

        if owned_cards and not matched:
            current = ", ".join(owned_cards)
            return f"No matching card found among your cards ({current}). Nothing removed."

        target = matched[0] if matched else card_name
        return f"Removed: {target}"
