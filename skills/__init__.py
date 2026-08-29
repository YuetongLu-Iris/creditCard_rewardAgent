"""
skills
------
Every capability the agent can call. To add a new skill:
  1. Create a new file here with a class implementing Skill (see base.py).
  2. Register an instance of it in ALL_SKILLS below.
No other file needs to change — the harness discovers tools from this list.
"""
from .spending_summary import SpendingSummarySkill
from .recommend_card import RecommendCardSkill
from .rewards_report import RewardsReportSkill
from .compare_cards import CompareCardsSkill
from .recommend_new_card import RecommendNewCardSkill
from .add_owned_card import AddOwnedCardSkill
from .remove_owned_card import RemoveOwnedCardSkill

ALL_SKILLS = [
    SpendingSummarySkill(),
    RecommendCardSkill(),
    RewardsReportSkill(),
    CompareCardsSkill(),
    RecommendNewCardSkill(),
    AddOwnedCardSkill(),
    RemoveOwnedCardSkill(),
]
