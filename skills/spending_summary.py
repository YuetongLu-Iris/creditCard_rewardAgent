"""
skills/spending_summary.py
---------------------------
Reports the user's spending broken down by category.
"""
from .base import Skill
from ._data import load_transactions


class SpendingSummarySkill(Skill):
    name = "get_spending_summary"
    description = (
        "Returns a summary of the user's spending broken down by category. "
        "Use this when the user asks about their spending habits, totals, "
        "or wants to know where their money is going."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": (
                    "Optional: filter by a specific category like "
                    "'Food and Drink' or 'Travel'. Omit to get all categories."
                ),
            }
        },
        "required": [],
    }

    def run(self, category: str | None = None) -> str:
        transactions = load_transactions()
        if not transactions:
            return "No transaction data found. Please run fetch_transactions.py first."

        category_totals: dict[str, float] = {}
        category_counts: dict[str, int] = {}

        for txn in transactions:
            if txn["amount"] <= 0:
                continue
            cat = txn["category"][0] if txn.get("category") else "Other"
            category_totals[cat] = category_totals.get(cat, 0) + txn["amount"]
            category_counts[cat] = category_counts.get(cat, 0) + 1

        if category:
            matched = {
                k: v for k, v in category_totals.items()
                if category.lower() in k.lower()
            }
            if not matched:
                return f"No spending found for category '{category}'."
            category_totals = matched

        lines = ["Spending Summary:"]
        total = 0.0
        for cat, amount in sorted(category_totals.items(), key=lambda x: -x[1]):
            count = category_counts.get(cat, 0)
            lines.append(f"  {cat}: ${amount:.2f} ({count} transactions)")
            total += amount
        lines.append(f"\nTotal: ${total:.2f}")
        return "\n".join(lines)
