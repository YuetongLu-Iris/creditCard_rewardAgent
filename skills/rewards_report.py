"""
skills/rewards_report.py
--------------------------
Returns the full rewards optimization report (earned vs. optimal per category).
"""
from .base import Skill
from ._data import load_rewards_report


class RewardsReportSkill(Skill):
    name = "get_rewards_report"
    description = (
        "Returns the full rewards optimization report showing how much the "
        "user earned vs could have earned with the optimal card per category. "
        "Use this when the user asks about missed rewards, optimization "
        "opportunities, or wants a full breakdown."
    )
    input_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def run(self) -> str:
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
