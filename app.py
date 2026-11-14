"""Pipeline board for the lead qualification agent.

Opens a CRM-style board in the browser. Press "Score leads" and the agent
scores each lead in data/leads.csv against data/scoring_rubric.json, then
moves it to Qualified (pushed to HubSpot, or the local mock CRM file) or
to the nurture list. Same scoring and CRM code as process_leads.py.

Run:
    python app.py
"""

import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from agent.crm_client import notify_slack, push_to_crm
from agent.llm import DEFAULT_MODEL
from agent.scoring import load_rubric, score_lead
from process_leads import load_leads

load_dotenv()

logger = logging.getLogger("lead-qualification")
app = FastAPI(title="Lead Qualification Agent")
WEB_DIR = Path(__file__).resolve().parent / "web"


class Lead(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    company_size: str = Field(default="unknown", max_length=40)
    budget: str = Field(default="not provided", max_length=40)
    timeline: str = Field(default="not provided", max_length=60)
    message: str = Field(default="", max_length=3000)


def qualify_lead(lead: dict) -> dict:
    """Score one lead and route it, exactly like process_leads.py does."""
    score = score_lead(lead)
    destination = None
    if score.qualified:
        destination = push_to_crm(lead, score)
        slack = notify_slack(lead, score)
        if slack:
            destination += f", {slack}"
    return {
        "score": score.score,
        "qualified": score.qualified,
        "reasoning": score.reasoning,
        "missing_info": score.missing_info,
        "destination": destination or "added to the nurture list",
    }


@app.get("/", include_in_schema=False)
def board():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/info")
def info():
    return {"model": os.getenv("LLM_MODEL") or DEFAULT_MODEL, "crm": "HubSpot" if os.getenv("HUBSPOT_ACCESS_TOKEN") else "Local mock CRM (output/crm_leads.csv)"}


@app.get("/api/leads")
def leads():
    return load_leads()


@app.get("/api/rubric")
def rubric():
    return load_rubric()


@app.post("/api/score")
def score(lead: Lead):
    started = time.perf_counter()
    try:
        result = qualify_lead(lead.model_dump())
    except Exception as exc:
        logger.exception("Scoring failed for %s", lead.email)
        detail = str(exc).splitlines()[0][:200] if str(exc) else ""
        return JSONResponse(status_code=502, content={"error": f"The agent could not score this lead ({type(exc).__name__}: {detail})."})
    return {**result, "email": lead.email, "seconds": round(time.perf_counter() - started, 1)}


if __name__ == "__main__":
    import threading
    import webbrowser

    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    uvicorn.run(app, host="127.0.0.1", port=port)
