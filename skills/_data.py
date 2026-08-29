"""
skills/_data.py
----------------
Shared JSON loading helpers used by multiple skills. Not a skill itself.
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent


def load_transactions() -> list[dict]:
    path = ROOT / "transactions.json"
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def load_rewards_report() -> dict:
    path = ROOT / "rewards_report.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def load_user_cards() -> list[dict]:
    path = ROOT / "user_cards.json"
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def save_user_cards(cards: list[dict]) -> None:
    path = ROOT / "user_cards.json"
    with open(path, "w") as f:
        json.dump(cards, f, indent=2)


def load_usage_log() -> list[dict]:
    path = ROOT / "card_usage_log.json"
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def save_usage_log(log: list[dict]) -> None:
    path = ROOT / "card_usage_log.json"
    with open(path, "w") as f:
        json.dump(log, f, indent=2)
