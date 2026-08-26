"""
main.py
-------
FastAPI backend that exposes the agent and rewards data to the React frontend.

Endpoints:
  POST /chat          — send a message to the LLM agent
  GET  /report        — get the full rewards report for the dashboard
  GET  /transactions  — get all transactions with category breakdown

Run:
    uvicorn main:app --reload
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import chat

# ── App Setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="Credit Card Rewards Agent API")

# Allow React dev server (port 5173) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory conversation store ──────────────────────────────────────────────
# Keyed by session_id so multiple browser tabs don't share history.
# In production you'd persist this in a database or Redis.
conversation_histories: dict[str, list[dict]] = {}


# ── Request / Response Models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    response: str
    session_id: str


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

    try:
        response_text, updated_history = chat(request.message, history)
        conversation_histories[session_id] = updated_history
        return ChatResponse(response=response_text, session_id=session_id)
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


@app.delete("/chat/{session_id}")
def clear_conversation(session_id: str):
    """Clear the conversation history for a session (reset chat)."""
    if session_id in conversation_histories:
        del conversation_histories[session_id]
    return {"status": "cleared", "session_id": session_id}
