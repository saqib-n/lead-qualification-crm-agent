"""Scores a lead against a rubric that's read from a file, not hardcoded.

The rubric (data/scoring_rubric.json) is what actually defines "qualified"
for a given business. Swap the file, not the code, to reuse this for a
different client with different criteria.

The model writes the score and the reasoning. Whether that score counts as
qualified is decided here in code against qualify_threshold, so a lead can
never score below the threshold and still be pushed to the CRM.
"""

import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent.llm import get_llm

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class ModelScore(BaseModel):
    """What the model is asked to produce."""

    score: int = Field(description="0 to 100, how well this lead matches the rubric")
    reasoning: str = Field(description="1-2 sentences explaining the score, specific to this lead")
    missing_info: list[str] = Field(
        default_factory=list,
        description="Fields that would help scoring but weren't clearly provided, e.g. 'budget'",
    )


class LeadScore(ModelScore):
    qualified: bool


def load_rubric() -> dict:
    with open(DATA_DIR / "scoring_rubric.json", "r", encoding="utf-8") as f:
        return json.load(f)


def score_lead(lead: dict, model: str | None = None, llm=None) -> LeadScore:
    rubric = load_rubric()

    system = SystemMessage(content=(
        "You score inbound sales leads against a rubric. Be honest and specific, "
        "don't inflate scores to be nice. A lead with a vague message and no real "
        "budget or timeline should score low, even if the company sounds promising. "
        "Score strictly based on the rubric criteria and what the lead actually said, "
        "not on assumptions about the company."
    ))
    human = HumanMessage(content=(
        f"Rubric:\n{json.dumps(rubric, indent=2)}\n\n"
        f"Lead:\n"
        f"Name: {lead['name']}\n"
        f"Company: {lead['company']} (size: {lead.get('company_size', 'unknown')})\n"
        f"Stated budget: {lead.get('budget', 'not provided')}\n"
        f"Stated timeline: {lead.get('timeline', 'not provided')}\n"
        f"Message: {lead.get('message', '')}\n\n"
        "Score this lead."
    ))

    llm = llm or get_llm(model)
    raw = llm.with_structured_output(ModelScore).invoke([system, human])

    score = max(0, min(100, raw.score))
    return LeadScore(
        score=score,
        reasoning=raw.reasoning,
        missing_info=raw.missing_info,
        qualified=score >= rubric["qualify_threshold"],
    )
