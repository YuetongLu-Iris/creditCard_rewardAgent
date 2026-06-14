"""
agent.py
--------
LLM-powered credit card rewards agent using Claude's tool-calling API.
The agent can answer natural language questions about your spending and
recommend the best card for any purchase.

Run:
    python agent.py
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent/ ".env")
import anthropic

from rewards_engine import CARDS, find_best_card, analyze_transactions

# ── Anthropic Client ──────────────────────────────────────────────────────────
client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from environment

# ── Tool Definitions ──────────────────────────────────────────────────────────
# These tell Claude what functions it can call and what each one does.

TOOLS = [
    {
        "name": "get_spending_summary",
        "description": (
            "Returns a summary of the user's spending broken down by category. "
            "Use this when the user asks about their spending habits, totals, "
            "or wants to know where their money is going."
        ),
        "input_schema": {
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
        },
    },
    {
        "name": "recommend_card",
        "description": (
            "Recommends the best credit card to use for a specific merchant "
            "or spending category to maximize rewards. Use this when the user "
            "asks which card to use for a purchase."
        ),
        "input_schema": {
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
        },
    },
    {
        "name": "get_rewards_report",
        "description": (
            "Returns the full rewards optimization report showing how much the "
            "user earned vs could have earned with the optimal card per category. "
            "Use this when the user asks about missed rewards, optimization "
            "opportunities, or wants a full breakdown."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "compare_cards",
        "description": (
            "Compares two or more credit cards side by side based on the user's "
            "actual spending patterns. Use this when the user asks whether they "
            "should get a new card or how cards compare."
        ),
        "input_schema": {
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
        },
    },
]


# ── Tool Implementations ──────────────────────────────────────────────────────

def load_transactions() -> list[dict]:
    path = Path(__file__).parent / "transactions.json"
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def load_rewards_report() -> dict:
    path = Path(__file__).parent / "rewards_report.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def tool_get_spending_summary(category: str | None = None) -> str:
    transactions = load_transactions()
    if not transactions:
        return "No transaction data found. Please run fetch_transactions.py first."

    category_totals: dict[str, float] = {}
    category_counts: dict[str, int]   = {}

    for txn in transactions:
        if txn["amount"] <= 0:
            continue
        cat = txn["category"][0] if txn.get("category") else "Other"
        category_totals[cat] = category_totals.get(cat, 0) + txn["amount"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    if category:
        # Try to match the requested category loosely
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


def tool_recommend_card(merchant_or_category: str) -> str:
    # Map common merchant/category names to Plaid categories
    keyword_map = {
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

    # Resolve to a Plaid category
    query   = merchant_or_category.lower()
    category = next(
        (plaid_cat for keyword, plaid_cat in keyword_map.items() if keyword in query),
        "Other",
    )

    # Find best card for a $100 hypothetical purchase in this category
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
        earned  = 100 * r / 100
        marker  = " ✅" if card.name == best_card.name else ""
        lines.append(f"  {card.name:<30} ${earned:.2f}  ({desc}){marker}")

    return "\n".join(lines)


def tool_get_rewards_report() -> str:
    report = load_rewards_report()
    if not report:
        return "No rewards report found. Please run rewards_engine.py first."

    lines = [
        f"Total spent:               ${report['total_spent']:.2f}",
        f"Max rewards (optimal mix): ${report['total_best_rewards']:.2f}",
        "",
        "By category:",
    ]
    for s in sorted(report["category_summaries"], key=lambda x: -x["total_spent"]):
        lines.append(
            f"  {s['category']:<22} ${s['total_spent']:>8.2f} spent  →  "
            f"best card: {s['best_card']} (${s['best_rewards']:.2f} rewards)"
        )
    return "\n".join(lines)


def tool_compare_cards(card_names: list[str]) -> str:
    report = load_rewards_report()
    if not report:
        return "No rewards report found. Please run rewards_engine.py first."

    # Find matching cards (case-insensitive partial match)
    matched_cards = []
    for name in card_names:
        for card in CARDS:
            if name.lower() in card.name.lower() and card not in matched_cards:
                matched_cards.append(card)

    if not matched_cards:
        available = ", ".join(c.name for c in CARDS)
        return f"Cards not found. Available cards: {available}"

    lines = ["Card Comparison (based on your actual spending):\n"]

    # Total rewards per card from the report
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


# ── Tool Dispatcher ───────────────────────────────────────────────────────────

def run_tool(tool_name: str, tool_input: dict) -> str:
    """Route Claude's tool call to the correct Python function."""
    if tool_name == "get_spending_summary":
        return tool_get_spending_summary(tool_input.get("category"))
    elif tool_name == "recommend_card":
        return tool_recommend_card(tool_input["merchant_or_category"])
    elif tool_name == "get_rewards_report":
        return tool_get_rewards_report()
    elif tool_name == "compare_cards":
        return tool_compare_cards(tool_input["card_names"])
    else:
        return f"Unknown tool: {tool_name}"


# ── Agent Loop ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a helpful credit card rewards optimization assistant.
You have access to the user's real spending data and a database of credit card
rewards rates. Your job is to help users maximize their cashback and points by
recommending the right card for each purchase and identifying missed rewards.

Always use the available tools to fetch real data before answering — never guess
or make up numbers. Be concise, friendly, and specific with dollar amounts."""


def chat(user_message: str, conversation_history: list[dict]) -> tuple[str, list[dict]]:
    """
    Send a message to the agent and return its response.
    Handles multi-step tool calling automatically.

    Returns (response_text, updated_history)
    """
    # Add user message to history
    conversation_history.append({"role": "user", "content": user_message})

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=conversation_history,
        )

        # If Claude wants to use a tool
        if response.stop_reason == "tool_use":
            # Add Claude's response (with tool calls) to history
            conversation_history.append({
                "role": "assistant",
                "content": response.content,
            })

            # Execute each tool and collect results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  🔧 Calling tool: {block.name}({block.input})")
                    result = run_tool(block.name, block.input)
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result,
                    })

            # Feed tool results back to Claude
            conversation_history.append({
                "role":    "user",
                "content": tool_results,
            })
            # Loop again so Claude can formulate its final response

        else:
            # Claude has a final text response
            response_text = next(
                (block.text for block in response.content if hasattr(block, "text")),
                "I couldn't generate a response.",
            )
            conversation_history.append({
                "role":    "assistant",
                "content": response_text,
            })
            return response_text, conversation_history


# ── CLI Chat Interface ────────────────────────────────────────────────────────

def main():
    print("\n" + "═"*60)
    print("  💳  Credit Card Rewards Agent")
    print("  Powered by Claude")
    print("═"*60)
    print("\nAsk me anything about your spending and rewards!")
    print("Examples:")
    print("  • Which card should I use at Whole Foods?")
    print("  • How much did I spend on dining last month?")
    print("  • Should I get the Amex Gold based on my spending?")
    print("  • Show me my full rewards report")
    print("\nType 'quit' to exit.\n")

    conversation_history = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "bye"):
            print("Goodbye!")
            break

        print()  # spacing
        response, conversation_history = chat(user_input, conversation_history)
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    main()
