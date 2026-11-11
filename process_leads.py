"""Score every lead in data/leads.csv against data/scoring_rubric.json,
push the qualified ones to the CRM (or a local mock file), and send the
rest to a nurture list.

Run:
    python process_leads.py
"""

import csv
from pathlib import Path

from dotenv import load_dotenv

from agent.crm_client import notify_slack, push_to_crm
from agent.scoring import load_rubric, score_lead

load_dotenv()

LEADS_FILE = Path(__file__).parent / "data" / "leads.csv"
OUTPUT_DIR = Path(__file__).parent / "output"
NURTURE_FILE = OUTPUT_DIR / "nurture_list.csv"
NURTURE_FIELDS = ["name", "email", "company", "score", "reasoning"]


def load_leads() -> list[dict]:
    with open(LEADS_FILE, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main():
    leads = load_leads()
    rubric = load_rubric()
    print(f"Scoring {len(leads)} leads against qualify_threshold={rubric['qualify_threshold']}\n")

    OUTPUT_DIR.mkdir(exist_ok=True)
    nurture_rows = []
    qualified_count = 0

    for lead in leads:
        score = score_lead(lead)
        print(f"{lead['name']} ({lead['company']}): {score.score}/100, qualified={score.qualified}")
        print(f"  {score.reasoning}")
        if score.missing_info:
            print(f"  Missing info: {', '.join(score.missing_info)}")

        if score.qualified:
            qualified_count += 1
            crm_result = push_to_crm(lead, score)
            print(f"  -> {crm_result}")
            slack_result = notify_slack(lead, score)
            if slack_result:
                print(f"  -> {slack_result}")
        else:
            nurture_rows.append({
                "name": lead["name"],
                "email": lead["email"],
                "company": lead["company"],
                "score": score.score,
                "reasoning": score.reasoning,
            })
        print()

    # Always rewrite it, an empty run shouldn't leave last run's list behind.
    with open(NURTURE_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=NURTURE_FIELDS)
        writer.writeheader()
        writer.writerows(nurture_rows)

    print(f"Done. {qualified_count} qualified, {len(nurture_rows)} sent to nurture list ({NURTURE_FILE.name}).")


if __name__ == "__main__":
    main()
