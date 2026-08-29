"""
skills/compare_cards.py
--------------------------
Compares two or more credit cards side by side on the user's actual spending.
"""
from .base import Skill
from ._data import load_rewards_report
from rewards_engine import CARDS


class CompareCardsSkill(Skill):
    name = "compare_cards"
    description = (
        "Compares two or more credit cards side by side based on the user's "
        "actual spending patterns. Use this when the user asks whether they "
        "should get a new card or how cards compare."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "card_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of card names to compare, e.g. "
                    "['Chase Sapphire Preferred', 'American Express Gold']. "
                    f"Available cards: {[c.name for c in CARDS]}"
                ),
            }
        },
        "required": ["card_names"],
    }

    def run(self, card_names: list[str]) -> str:
        report = load_rewards_report()
        if not report:
            return "No rewards report found. Please run rewards_engine.py first."

        matched_cards = []
        for name in card_names:
            for card in CARDS:
                if name.lower() in card.name.lower() and card not in matched_cards:
                    matched_cards.append(card)

        if not matched_cards:
            available = ", ".join(c.name for c in CARDS)
            return f"Cards not found. Available cards: {available}"

        lines = ["Card Comparison (based on your actual spending):\n"]

        for card in matched_cards:
            total_rewards = sum(
                s["all_card_rewards"].get(card.name, 0)
                for s in report["category_summaries"]
            )
            lines.append(f"  {card.name}")
            lines.append(f"    Total rewards on your spending: ${total_rewards:.2f}")
            lines.append(f"    Base rate: {card.base_rate}x on all purchases")
            for rate in card.rates:
                lines.append(f"    {rate.category}: {rate.multiplier}x ({rate.description})")
            lines.append("")

        return "\n".join(lines)
