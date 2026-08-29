"""
main.py
-------
FastAPI backend that exposes the agent and rewards data to the React frontend.

Endpoints:
  POST /chat                — send a message to the LLM agent
  GET  /report               — get the full rewards report for the dashboard
  GET  /transactions         — get all transactions with category breakdown
  GET  /wallet                — get the user's owned cards with usage stats
  POST /confirm_card_usage   — record which card the user actually used

Run:
    uvicorn main:app --reload
"""

import json
import os
from dataclasses import asdict
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import chat
from rewards_engine import CARDS
from skills._data import load_user_cards, save_user_cards, load_rewards_report, load_usage_log, save_usage_log

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


class ChatResponse(BaseModel):
    response: str
    session_id: str
    confirm_card_options: list[str] | None = None  # shown as "which card did you use?" chips


class ConfirmCardUsageRequest(BaseModel):
    card_name: str
    context: str = ""
    session_id: str = "default"


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "message": "Rewards Agent API is running"}


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

    history = conversation_histories[session_id]

    image = None
    if request.image_base64:
        if not request.image_media_type:
            raise HTTPException(status_code=400, detail="image_media_type is required when image_base64 is set.")
        image = {"media_type": request.image_media_type, "data": request.image_base64}

    if not request.message and not image:
        raise HTTPException(status_code=400, detail="Provide a message, an image, or both.")

    try:
        response_text, updated_history, tools_used = chat(request.message, history, image=image)
        conversation_histories[session_id] = updated_history

        confirm_options = None
        if "recommend_card" in tools_used:
            owned_names = [c["card_name"] for c in load_user_cards()]
            confirm_options = owned_names + ["Other"]

        return ChatResponse(response=response_text, session_id=session_id, confirm_card_options=confirm_options)
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


@app.get("/wallet")
def get_wallet():
    """
    Return the user's owned cards (user_cards.json), each enriched with its
    catalog details (cards_catalog.json) and — where available — how much
    it would have earned against the user's actual spending history
    (rewards_report.json), so the dashboard can show real usage relevance
    rather than just a static card description.
    """
    owned = load_user_cards()
    catalog_by_name = {c.name: c for c in CARDS}
    report = load_rewards_report()
    usage_log = load_usage_log()

    cards = []
    for entry in owned:
        card = catalog_by_name.get(entry["card_name"])
        if card is None:
            continue  # catalog entry missing/renamed; skip defensively

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

        actual_uses = [u for u in usage_log if u["card_name"].lower() == card.name.lower()]

        cards.append({
            "name": card.name,
            "annual_fee": card.annual_fee,
            "base_rate": card.base_rate,
            "description": card.description,
            "official_url": card.official_url,
            "rates": [asdict(r) for r in card.rates],
            "highlight": _card_highlight(card),
            "added_date": entry.get("added_date"),
            "usage": usage,
            "actual_usage_count": len(actual_uses),
            "actual_usage_recent": [u["context"] for u in actual_uses[-3:] if u.get("context")],
        })

    return {"cards": cards}


@app.post("/confirm_card_usage")
def confirm_card_usage(request: ConfirmCardUsageRequest):
    """
    Records which card the user actually used for a recommended purchase.
    Called directly by the frontend when the user picks a card from the
    confirmation chips shown after a recommendation — deliberately not
    routed through the LLM, since it's a deterministic data write with
    nothing to reason about.
    """
    log = load_usage_log()
    log.append({
        "card_name": request.card_name,
        "context": request.context,
        "date": date.today().isoformat(),
    })
    save_usage_log(log)

    # Confirming usage implies ownership — add it to the wallet if it isn't
    # there yet and matches a card we already know about. (If it doesn't
    # match anything, the usage is still logged; the user can fully "add"
    # it with reward-rate detail by telling the agent "I have ___" in chat.)
    owned = load_user_cards()
    already_owned = any(c["card_name"].lower() == request.card_name.lower() for c in owned)
    if not already_owned:
        query = request.card_name.lower()
        catalog_match = next(
            (c for c in CARDS if query in c.name.lower() or c.name.lower() in query),
            None,
        )
        if catalog_match:
            owned.append({"card_name": catalog_match.name, "added_date": date.today().isoformat()})
            save_user_cards(owned)

    return {"status": "recorded"}


@app.delete("/chat/{session_id}")
def clear_conversation(session_id: str):
    """Clear the conversation history for a session (reset chat)."""
    if session_id in conversation_histories:
        del conversation_histories[session_id]
    return {"status": "cleared", "session_id": session_id}
