from fastapi.testclient import TestClient

import app as web
from agent import crm_client, scoring
from tests.fakes import FakeStructuredLLM


def test_board_and_score_api(monkeypatch, tmp_path):
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(crm_client, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(crm_client, "LOCAL_CRM_FILE", tmp_path / "crm_leads.csv")
    real_score_lead = scoring.score_lead
    scores = iter([85, 20])
    monkeypatch.setattr(web, "score_lead", lambda lead: real_score_lead(
        lead, llm=FakeStructuredLLM(scoring.ModelScore(score=next(scores), reasoning="r", missing_info=["budget"]))))
    client = TestClient(web.app)

    assert "Score leads" in client.get("/").text
    assert len(client.get("/api/leads").json()) == 5
    assert client.get("/api/rubric").json()["qualify_threshold"] == 60

    lead = {"name": "Rachel Kim", "email": "rachel.kim@example.com", "company": "Horizon Fitness"}
    hot = client.post("/api/score", json=lead).json()
    assert hot["qualified"] is True and "mock CRM" in hot["destination"]
    assert (tmp_path / "crm_leads.csv").exists()

    cold = client.post("/api/score", json=lead).json()
    assert cold["qualified"] is False and cold["destination"] == "added to the nurture list"
    assert client.post("/api/score", json={**lead, "name": ""}).status_code == 422
