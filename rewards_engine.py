"""
rewards_engine.py
-----------------
Maps spending transactions to credit card rewards rates and calculates:
  - Rewards earned with your current card(s)
  - Rewards you COULD earn with the optimal card
  - The gap (money left on the table)

Run standalone to see a full rewards report:
    python3 rewards_engine.py
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

CARDS_CATALOG_PATH = Path(__file__).parent / "cards_catalog.json"

# ── Category Normalization ────────────────────────────────────────────────────
# Maps new Plaid SNAKE_CASE primaries (after underscore→space) to legacy names
# used in the card database. Only needed where the strings genuinely differ.
_CATEGORY_ALIASES: dict[str, str] = {
   "food and drink":       "food and drink",
    "general merchandise":  "shops",
    "entertainment":        "recreation",
    "personal care":        "healthcare",
    "medical":              "healthcare",
    "groceries":            "food and drink",
    "restaurants":          "food and drink",
    "transportation":       "travel",        # map Uber/transit to travel
    "rent and utilities":   "service",
}


def _normalize_category(category: str) -> str:
    """Lowercase + underscore→space, then apply legacy alias if one exists."""
    normalized = category.replace("_", " ").lower()
    return _CATEGORY_ALIASES.get(normalized, normalized)


# ── Data Models ───────────────────────────────────────────────────────────────

@dataclass
class RewardsRate:
    """Rewards rate for a specific spending category on a card."""
    category: str       # Plaid top-level category e.g. "Food and Drink"
    multiplier: float   # e.g. 3.0 = 3x points or 3% cashback
    description: str    # Human-readable e.g. "3x points on dining"


@dataclass
class CreditCard:
    """A credit card with its rewards structure."""
    name: str
    base_rate: float                        # fallback rate for uncategorized spend
    rates: list[RewardsRate] = field(default_factory=list)
    annual_fee: float = 0.0
    description: str = ""
    official_url: str = ""                  # link to the issuer's official card/rewards page
    source: str = "seed"                    # "seed" (curated) or "web_search" (discovered live)
    last_updated: str | None = None         # ISO date; None for hand-curated seed entries

    def get_rate_for_category(self, category: str) -> tuple[float, str]:
        """
        Return (multiplier, description) for the given Plaid category.
        Falls back to base_rate if no specific rate exists. When a card has
        multiple sub-tiered rates for the same category (e.g. a higher rate
        for bookings through the issuer's portal vs. direct), the best one
        is returned rather than whichever happened to be listed first.
        """
        normalized = _normalize_category(category)
        matches = [r for r in self.rates if _normalize_category(r.category) == normalized]
        if matches:
            best = max(matches, key=lambda r: r.multiplier)
            return best.multiplier, best.description
        return self.base_rate, f"{self.base_rate}x on all other purchases"


# ── Card Database ─────────────────────────────────────────────────────────────
# Cards live in cards_catalog.json (seeded with a handful of well-known cards).
# New cards discovered via web search (see skills/add_owned_card.py and
# skills/recommend_new_card.py) get appended here at runtime and persisted back.

def _card_from_dict(d: dict) -> CreditCard:
    return CreditCard(
        name=d["name"],
        base_rate=d["base_rate"],
        rates=[RewardsRate(**r) for r in d.get("rates", [])],
        annual_fee=d.get("annual_fee", 0.0),
        description=d.get("description", ""),
        official_url=d.get("official_url", ""),
        source=d.get("source", "seed"),
        last_updated=d.get("last_updated"),
    )


def load_cards_catalog() -> list[CreditCard]:
    if not CARDS_CATALOG_PATH.exists():
        return []
    with open(CARDS_CATALOG_PATH) as f:
        return [_card_from_dict(d) for d in json.load(f)]


def save_cards_catalog(cards: list[CreditCard]) -> None:
    with open(CARDS_CATALOG_PATH, "w") as f:
        json.dump([asdict(c) for c in cards], f, indent=2)


CARDS: list[CreditCard] = load_cards_catalog()


# ── Core Engine ───────────────────────────────────────────────────────────────

@dataclass
class TransactionResult:
    """Rewards analysis for a single transaction."""
    date: str
    merchant: str
    amount: float
    category: str
    best_card: str
    best_rate: float
    best_rewards: float         # amount * best_rate / 100 (in points/cashback $)
    best_description: str


@dataclass
class CategorySummary:
    """Aggregated rewards summary for a spending category."""
    category: str
    total_spent: float
    best_card: str
    best_rate: float
    best_rewards: float
    all_card_rewards: dict[str, float]  # card name → total rewards


def find_best_card(category: str, amount: float) -> tuple[CreditCard, float, str]:
    """
    Given a spending category and amount, find the card that
    earns the most rewards.

    Returns (best_card, rewards_earned, rate_description)
    """
    best_card     = CARDS[0]
    best_rate     = 0.0
    best_desc     = ""
    best_rewards  = 0.0

    for card in CARDS:
        rate, desc = card.get_rate_for_category(category)
        rewards    = amount * rate / 100  # treating multiplier as cashback %
        if rewards > best_rewards:
            best_rewards = rewards
            best_rate    = rate
            best_desc    = desc
            best_card    = card

    return best_card, best_rewards, best_desc


def analyze_transactions(transactions: list[dict]) -> dict:
    """
    Run the full rewards analysis over a list of Plaid transactions.

    Returns a structured report with:
      - per-transaction results
      - per-category summaries
      - overall totals
    """
    transaction_results: list[TransactionResult] = []
    category_data: dict[str, dict] = {}
    SKIP_CATEGORIES = {"transfer_out", "transfer_in", "loan_payments", "transfer", "payment"}
    for txn in transactions:
        # Skip credits / refunds

        if txn["amount"] <= 0:
            continue
        if txn["category"][0].lower().strip() in SKIP_CATEGORIES:
            continue
        amount   = txn["amount"]
        merchant = txn.get("merchant_name") or txn.get("name", "Unknown")
        category = txn["category"][0] if txn.get("category") else "Other"

        best_card, best_rewards, best_desc = find_best_card(category, amount)

        # Per-transaction result
        transaction_results.append(TransactionResult(
            date            = txn["date"],
            merchant        = merchant,
            amount          = amount,
            category        = category,
            best_card       = best_card.name,
            best_rate       = best_card.get_rate_for_category(category)[0],
            best_rewards    = best_rewards,
            best_description= best_desc,
        ))

        # Accumulate category-level data
        if category not in category_data:
            category_data[category] = {
                "total_spent":      0.0,
                "best_card":        best_card.name,
                "best_rate":        best_card.get_rate_for_category(category)[0],
                "best_rewards":     0.0,
                "all_card_rewards": {c.name: 0.0 for c in CARDS},
            }

        cat = category_data[category]
        cat["total_spent"]  += amount
        cat["best_rewards"] += best_rewards

        # Also track what each card would have earned
        for card in CARDS:
            rate, _ = card.get_rate_for_category(category)
            cat["all_card_rewards"][card.name] += amount * rate / 100

    # Build category summaries
    category_summaries = []
    for cat_name, data in category_data.items():
        # Recalculate best card based on accumulated totals
        best_card_name = max(data["all_card_rewards"], key=data["all_card_rewards"].get)
        category_summaries.append(CategorySummary(
            category          = cat_name,
            total_spent       = data["total_spent"],
            best_card         = best_card_name,
            best_rate         = data["best_rate"],
            best_rewards      = data["all_card_rewards"][best_card_name],
            all_card_rewards  = data["all_card_rewards"],
        ))

    # Overall totals
    total_spent       = sum(r.amount for r in transaction_results)
    total_best_rewards= sum(s.best_rewards for s in category_summaries)

    return {
        "transactions":        transaction_results,
        "category_summaries":  category_summaries,
        "total_spent":         total_spent,
        "total_best_rewards":  total_best_rewards,
    }


def print_report(report: dict) -> None:
    """Print a human-readable rewards optimization report."""

    print("\n" + "═"*65)
    print("  💳  CREDIT CARD REWARDS OPTIMIZATION REPORT")
    print("═"*65)

    # ── Category Breakdown ────────────────────────────────────────────────────
    print("\n📊  BEST CARD BY SPENDING CATEGORY\n")
    print(f"  {'CATEGORY':<22} {'SPENT':>8}  {'BEST CARD':<28} {'REWARDS':>8}")
    print(f"  {'─'*22} {'─'*8}  {'─'*28} {'─'*8}")

    summaries: list[CategorySummary] = report["category_summaries"]
    for s in sorted(summaries, key=lambda x: -x.total_spent):
        print(
            f"  {s.category:<22} ${s.total_spent:>7.2f}  "
            f"{s.best_card:<28} ${s.best_rewards:>7.2f}"
        )

    # ── All Cards Comparison ──────────────────────────────────────────────────
    print("\n\n🏆  TOTAL REWARDS EARNED PER CARD (if used for ALL spending)\n")
    card_totals: dict[str, float] = {c.name: 0.0 for c in CARDS}
    for s in summaries:
        for card_name, rewards in s.all_card_rewards.items():
            card_totals[card_name] += rewards

    for card_name, total in sorted(card_totals.items(), key=lambda x: -x[1]):
        bar = "█" * int(total * 2)
        print(f"  {card_name:<30} ${total:>7.2f}  {bar}")

    # ── Totals ────────────────────────────────────────────────────────────────
    print(f"\n\n{'─'*65}")
    print(f"  Total spent:              ${report['total_spent']:>8.2f}")
    print(f"  Max rewards (optimal mix): ${report['total_best_rewards']:>8.2f}")
    print(f"{'═'*65}\n")


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    transactions_path = Path(__file__).parent / "transactions.json"

    if not transactions_path.exists():
        print("❌  transactions.json not found.")
        print("    Run fetch_transactions.py first to generate it.")
        return

    print(f"📂  Loading transactions from {transactions_path}…")
    with open(transactions_path) as f:
        transactions = json.load(f)

    print(f"✅  Loaded {len(transactions)} transactions\n")

    report = analyze_transactions(transactions)
    print_report(report)

    # Save report for the LLM agent to use later
    report_path = Path(__file__).parent / "rewards_report.json"
    serializable = {
        "total_spent":        report["total_spent"],
        "total_best_rewards": report["total_best_rewards"],
        "category_summaries": [
            {
                "category":         s.category,
                "total_spent":      s.total_spent,
                "best_card":        s.best_card,
                "best_rewards":     s.best_rewards,
                "all_card_rewards": s.all_card_rewards,
            }
            for s in report["category_summaries"]
        ],
    }
    with open(report_path, "w") as f:
        json.dump(serializable, f, indent=2)
    print(f"💾  Rewards report saved to rewards_report.json — ready for the agent!")


if __name__ == "__main__":
    main()
