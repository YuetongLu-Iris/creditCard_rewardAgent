"""
fetch_transactions.py
---------------------
Day-1 script: connect to Plaid Sandbox and print your transactions.

Run:
    pip install plaid-python python-dotenv
    python fetch_transactions.py
"""

import os
import json
from datetime import date, timedelta
from dotenv import load_dotenv

from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.model.accounts_get_request import AccountsGetRequest

from plaid_client import get_plaid_client, create_sandbox_access_token

# ── Load .env ─────────────────────────────────────────────────────────────────
load_dotenv()

# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch_accounts(client, access_token: str) -> list[dict]:
    """Return a list of linked accounts (id, name, type, balance)."""
    request  = AccountsGetRequest(access_token=access_token)
    response = client.accounts_get(request)

    accounts = []
    for acct in response["accounts"]:
        accounts.append({
            "account_id":   acct["account_id"],
            "name":         acct["name"],
            "type":         str(acct["type"]),
            "subtype":      str(acct["subtype"]),
            "balance":      acct["balances"]["current"],
            "currency":     acct["balances"]["iso_currency_code"],
        })
    return accounts

def infer_category(merchant_name: str) -> list[str]:
    """Fallback category inference based on merchant name keywords."""
    merchant = merchant_name.lower()

    dining_keywords   = ["restaurant", "cafe", "coffee", "mcdonald", "starbucks",
                         "chipotle", "subway", "pizza", "sushi", "grill", "burger",
                         "taco", "doordash", "ubereats", "grubhub"]
    travel_keywords   = ["airline", "airways", "united", "delta", "marriott",
                         "hilton", "hotel", "airbnb", "uber", "lyft", "parking",
                         "hertz", "avis", "amtrak"]
    shopping_keywords = ["amazon", "walmart", "target", "costco", "ebay",
                         "apple", "best buy", "nike", "zara", "h&m"]
    health_keywords   = ["pharmacy", "cvs", "walgreens", "hospital", "clinic",
                         "dental", "doctor", "medical"]

    if any(k in merchant for k in dining_keywords):
        return ["Food and Drink", "Restaurants"]
    if any(k in merchant for k in travel_keywords):
        return ["Travel", "Airlines and Aviation Services"]
    if any(k in merchant for k in shopping_keywords):
        return ["Shops", "Retail"]
    if any(k in merchant for k in health_keywords):
        return ["Healthcare", "Pharmacies"]

    return ["Other"]

def fetch_transactions(
    client,
    access_token: str,
    days_back: int = 30,
    max_results: int = 50,
) -> list[dict]:
    """
    Return up to `max_results` transactions from the last `days_back` days.

    Each transaction dict contains the fields most useful for a
    rewards-optimisation agent: merchant name, amount, category, and date.
    """
    end_date   = date.today()
    start_date = end_date - timedelta(days=days_back)

    options = TransactionsGetRequestOptions(
        count=max_results,
        offset=0,
        include_personal_finance_category=True,
    )
    request = TransactionsGetRequest(
        access_token=access_token,
        start_date=start_date,
        end_date=end_date,
        options=options,
    )
    response = client.transactions_get(request)

    transactions = []
    for txn in response["transactions"]:
        pfc = txn.get("personal_finance_category") or {}
        raw_category = txn.get("category") or []
        if pfc:
            category = [pfc.get("primary", "Other"), pfc.get("detailed", "")]
        elif raw_category:
            category = raw_category
        else:
            category = infer_category(txn.get("merchant_name") or txn["name"])
        transactions.append({
            "transaction_id": txn["transaction_id"],
            "date":           str(txn["date"]),
            "name":           txn["name"],
            "amount":         txn["amount"],                      # positive = debit
            "category":       category,
            "merchant_name":  txn.get("merchant_name") or txn["name"],
            "account_id":     txn["account_id"],
        })
    return transactions


def pretty_print_transactions(transactions: list[dict]) -> None:
    """Print a human-readable summary of transactions."""
    print(f"\n{'─'*60}")
    print(f"  {'DATE':<12} {'MERCHANT':<25} {'CATEGORY':<20} {'AMOUNT':>8}")
    print(f"{'─'*60}")
    for txn in transactions:
        category = txn["category"][0] if txn["category"] else "Unknown"
        print(
            f"  {txn['date']:<12} "
            f"{txn['merchant_name'][:24]:<25} "
            f"{category[:19]:<20} "
            f"${txn['amount']:>7.2f}"
        )
    print(f"{'─'*60}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    client = get_plaid_client()

    # Create a sandbox access token (simulates a user linking their bank)
    # In Week 3 you'll store this in a database instead of recreating it
    import time

    print("🔗  Creating sandbox session…")
    access_token = create_sandbox_access_token(client)
    print("⏳  Waiting for Plaid to prepare transaction data…")
    time.sleep(10)

    # ── Accounts ──────────────────────────────────────────────────────────────
    print("\n📂  Linked accounts:")
    accounts = fetch_accounts(client, access_token)
    for acct in accounts:
        print(f"   • {acct['name']} ({acct['subtype']})  —  "
              f"Balance: {acct['currency']} {acct['balance']:.2f}")

    # ── Transactions ──────────────────────────────────────────────────────────
    print("\n📋  Recent transactions (last 30 days):")
    transactions = fetch_transactions(client, access_token, days_back=30)

    if not transactions:
        print("   No transactions found — try increasing days_back.")
        return

    pretty_print_transactions(transactions)

    # ── Spending by category ──────────────────────────────────────────────────
    print("📊  Spending by top-level category:")
    category_totals: dict[str, float] = {}
    for txn in transactions:
        if txn["amount"] <= 0:          # skip refunds / credits
            continue
        cat = txn["category"][0] if txn["category"] else "Other"
        category_totals[cat] = category_totals.get(cat, 0) + txn["amount"]

    for cat, total in sorted(category_totals.items(), key=lambda x: -x[1]):
        print(f"   {cat:<30}  ${total:>8.2f}")

    # Save raw data for the next step (rewards engine)
    with open("transactions.json", "w") as f:
        json.dump(transactions, f, indent=2)
    print("\n💾  Raw data saved to transactions.json — ready for the rewards engine!")


if __name__ == "__main__":
    main()
