"""
skills/recommend_card.py
--------------------------
Recommends the best credit card for a merchant or spending category.
"""
from .base import Skill
from rewards_engine import CARDS, find_best_card

_KEYWORD_MAP = {
    "dining":      "Food and Drink",
    "restaurant":  "Food and Drink",
    "food":        "Food and Drink",
    "groceries":   "Food and Drink",
    "grocery":     "Food and Drink",
    "coffee":      "Food and Drink",
    "travel":      "Travel",
    "flight":      "Travel",
    "airline":     "Travel",
    "hotel":       "Travel",
    "shopping":    "Shops",
    "shop":        "Shops",
    "retail":      "Shops",
    "amazon":      "Shops",
    "healthcare":  "Healthcare",
    "pharmacy":    "Healthcare",
    "drugstore":   "Healthcare",
}


class RecommendCardSkill(Skill):
    name = "recommend_card"
    description = (
        "Recommends the best credit card to use for a specific merchant "
        "or spending category to maximize rewards. Use this when the user "
        "asks which card to use for a purchase."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "merchant_or_category": {
                "type": "string",
                "description": (
                    "The merchant name (e.g. 'Whole Foods', 'United Airlines') "
                    "or spending category (e.g. 'dining', 'travel', 'groceries')."
                ),
            }
        },
        "required": ["merchant_or_category"],
    }

    def run(self, merchant_or_category: str) -> str:
        query = merchant_or_category.lower()
        category = next(
            (plaid_cat for keyword, plaid_cat in _KEYWORD_MAP.items() if keyword in query),
            "Other",
        )

        best_card, rewards, description = find_best_card(category, 100)
        rate, _ = best_card.get_rate_for_category(category)

        lines = [
            f"Best card for '{merchant_or_category}': {best_card.name}",
            f"  Rewards rate: {rate}x ({description})",
            f"  On a $100 purchase you'd earn: ${rewards:.2f} back",
            "",
            "All cards compared (per $100 spent):",
        ]
        for card in CARDS:
            r, desc = card.get_rate_for_category(category)
            earned = 100 * r / 100
            marker = " ✅" if card.name == best_card.name else ""
            lines.append(f"  {card.name:<30} ${earned:.2f}  ({desc}){marker}")

        return "\n".join(lines)
