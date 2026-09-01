"""
main.py
-------
FastAPI backend that exposes the agent and rewards data to the React frontend.

The user's owned-cards list and confirmed-usage log live in the browser
(localStorage), not here — Render's free tier has no persistent disk, so
anything written to a server-side file gets wiped on the next deploy. This
backend is stateless with respect to that data: /chat receives the current
owned-cards list as input and returns signals (confirm_card_options,
pending_purchase, wallet_action) the frontend applies to its own local
state; /wallet takes card names as input and returns computed enrichment
(catalog details + rewards relevance) without storing anything.

Endpoints:
  POST /chat           — send a message to the LLM agent
  GET  /report          — get the full rewards report for the dashboard
  GET  /transactions    — get all transactions with category breakdown
  POST /wallet           — enrich a list of owned card names with catalog +
                            rewards-relevance data (stateless)

Run:
    uvicorn main:app --reload
"""

import json
import os
from dataclasses import asdict
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import chat
from rewards_engine import CARDS
from skills._data import load_rewards_report

# ── App Setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="Credit Card Rewards Agent API")

# Allow React dev server (port 5173) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory conversation store ──────────────────────────────────────────────
# Keyed by session_id so multiple browser tabs don't share history.
# In production you'd persist this in a database or Redis.
conversation_histories: dict[str, list[dict]] = {}


# ── Request / Response Models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = ""
    session_id: str = "default"
    image_base64: str | None = None       # raw base64, no data: URL prefix
    image_media_type: str | None = None   # e.g. "image/jpeg", "image/png"
    owned_cards: list[str] = []           # from the frontend's local wallet state


class ChatResponse(BaseModel):
    response: str
    session_id: str
    confirm_card_options: list[str] | None = None  # shown as "which card did you use?" chips
    pending_purchase: dict | None = None            # {merchant_or_category, amount} for the chips above
    wallet_action: dict | None = None                # {"type": "add", "card": {...}} or {"type": "remove", "card_name": ...}


class WalletRequest(BaseModel):
    card_names: list[str] = []


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "message": "Rewards Agent API is running"}


def _find_in_catalog(name: str):
    query = name.lower()
    for card in CARDS:
        if query in card.name.lower() or card.name.lower() in query:
            return card
    return None


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """
    Send a message to the LLM agent and get a response.
    Maintains conversation history per session.
    """
    session_id = request.session_id

    # Retrieve or create conversation history for this session
    if session_id not in conversation_histories:
        conversation_histories[session_id] = []

    image = None
    if request.image_base64:
        if not request.image_media_type:
            raise HTTPException(status_code=400, detail="image_media_type is required when image_base64 is set.")
        image = {"media_type": request.image_media_type, "data": request.image_base64}

    if not request.message and not image:
        raise HTTPException(status_code=400, detail="Provide a message, an image, or both.")

    # Pass a copy: chat() mutates the list in place as it goes, so on any
    # failure partway through, the copy is discarded and the stored session
    # keeps its last-known-good state instead of being left half-written.
    history = list(conversation_histories[session_id])

    try:
        response_text, updated_history, tool_calls = chat(
            request.message, history, image=image, owned_cards=request.owned_cards,
        )
        conversation_histories[session_id] = updated_history

        confirm_options = None
        pending_purchase = None
        recommend_call = next((c for c in tool_calls if c["name"] == "recommend_card"), None)
        if recommend_call:
            confirm_options = list(request.owned_cards) + ["Other"]
            pending_purchase = {
                "merchant_or_category": recommend_call["input"].get("merchant_or_category"),
                "amount": recommend_call["input"].get("amount"),
            }

        wallet_action = None
        add_call = next((c for c in tool_calls if c["name"] == "add_owned_card"), None)
        remove_call = next((c for c in tool_calls if c["name"] == "remove_owned_card"), None)
        if add_call:
            card = _find_in_catalog(add_call["input"].get("card_name", ""))
            if card:
                wallet_action = {"type": "add", "card": asdict(card)}
        elif remove_call:
            wallet_action = {"type": "remove", "card_name": remove_call["input"].get("card_name")}

        return ChatResponse(
            response=response_text,
            session_id=session_id,
            confirm_card_options=confirm_options,
            pending_purchase=pending_purchase,
            wallet_action=wallet_action,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/report")
def get_report():
    """
    Return the rewards optimization report for the dashboard.
    Run rewards_engine.py first to generate rewards_report.json.
    """
    report_path = Path(__file__).parent / "rewards_report.json"
    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail="rewards_report.json not found. Run rewards_engine.py first."
        )
    with open(report_path) as f:
        return json.load(f)


@app.get("/transactions")
def get_transactions():
    """
    Return all transactions with a category spending breakdown.
    Run fetch_transactions.py first to generate transactions.json.
    """
    transactions_path = Path(__file__).parent / "transactions.json"
    if not transactions_path.exists():
        raise HTTPException(
            status_code=404,
            detail="transactions.json not found. Run fetch_transactions.py first."
        )

    with open(transactions_path) as f:
        transactions = json.load(f)

    # Build category breakdown
    category_totals: dict[str, float] = {}
    category_counts: dict[str, int]   = {}

    SKIP_CATEGORIES = {"transfer_out", "transfer_in", "loan_payments", "transfer", "payment"}

    for txn in transactions:
        if txn["amount"] <= 0:
            continue
        cat = txn["category"][0] if txn.get("category") else "Other"
        if cat.lower().strip() in SKIP_CATEGORIES:
            continue
        category_totals[cat] = category_totals.get(cat, 0) + txn["amount"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    category_breakdown = [
        {
            "category": cat,
            "total":    round(amount, 2),
            "count":    category_counts[cat],
        }
        for cat, amount in sorted(category_totals.items(), key=lambda x: -x[1])
    ]

    return {
        "transactions":        transactions,
        "category_breakdown":  category_breakdown,
        "total_transactions":  len(transactions),
        "total_spent":         round(sum(t["amount"] for t in transactions if t["amount"] > 0), 2),
    }


def _card_highlight(card) -> str:
    if card.rates:
        best = max(card.rates, key=lambda r: r.multiplier)
        return f"{best.multiplier:g}x {best.category}"
    return f"{card.base_rate:g}x on everything"


@app.post("/wallet")
def get_wallet(request: WalletRequest):
    """
    Given the card names the frontend currently has in its local wallet,
    return each one enriched with catalog details (cards_catalog.json) and
    — where available — how much it would have earned against the user's
    actual spending history (rewards_report.json). Stateless: nothing here
    is stored server-side, and confirmed-usage stats are computed by the
    frontend from its own local log, not returned here.
    """
    report = load_rewards_report()

    cards = []
    for name in request.card_names:
        card = _find_in_catalog(name)
        if card is None:
            continue  # not in the shared catalog (yet) — frontend keeps its own copy

        usage = []
        for s in report.get("category_summaries", []):
            card_rewards = s.get("all_card_rewards", {}).get(card.name)
            if card_rewards is None:
                continue
            usage.append({
                "category": s["category"],
                "spent": s["total_spent"],
                "rewards_if_used": round(card_rewards, 2),
                "is_best_card": s.get("best_card") == card.name,
            })
        usage.sort(key=lambda u: -u["spent"])

        cards.append({
            "name": card.name,
            "annual_fee": card.annual_fee,
            "base_rate": card.base_rate,
            "description": card.description,
            "official_url": card.official_url,
            "rates": [asdict(r) for r in card.rates],
            "highlight": _card_highlight(card),
            "usage": usage,
        })

    return {"cards": cards}


@app.delete("/chat/{session_id}")
def clear_conversation(session_id: str):
    """Clear the conversation history for a session (reset chat)."""
    if session_id in conversation_histories:
        del conversation_histories[session_id]
    return {"status": "cleared", "session_id": session_id}
