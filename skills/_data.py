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
