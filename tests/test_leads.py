import csv

import pytest

from agent import crm_client, scoring
from tests.fakes import FakeStructuredLLM

LEAD = {"name": "Rachel Kim", "email": "rachel.kim@example.com", "company": "Horizon Fitness"}


def score(value, threshold_lead=LEAD):
    llm = FakeStructuredLLM(scoring.ModelScore(score=value, reasoning="r"))
    return scoring.score_lead(threshold_lead, llm=llm)


def test_threshold_decides_qualified_not_the_model():
    threshold = scoring.load_rubric()["qualify_threshold"]
    assert score(threshold).qualified is True
    assert score(threshold - 1).qualified is False


def test_scores_are_clamped():
    assert score(130).score == 100
    assert score(-5).score == 0


def test_local_crm_updates_instead_of_duplicating(tmp_path, monkeypatch):
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(crm_client, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(crm_client, "LOCAL_CRM_FILE", tmp_path / "crm_leads.csv")
    crm_client.push_to_crm(LEAD, score(70))
    crm_client.push_to_crm(LEAD, score(90))
    with open(tmp_path / "crm_leads.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1 and rows[0]["score"] == "90"


class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code, self.body = status, body or {}

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.mark.parametrize("existing", [False, True])
def test_hubspot_contact_then_note(monkeypatch, existing):
    monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "test-token")
    calls = []

    def fake_request(method, url, headers, timeout, json):
        calls.append((method, url.removeprefix(crm_client.HUBSPOT_API), json))
        if url.endswith("/contacts"):
            return FakeResponse(409) if existing else FakeResponse(201, {"id": "new-1"})
        if url.endswith("/search"):
            return FakeResponse(200, {"results": [{"id": "old-7"}]})
        return FakeResponse(201, {"id": "note-1"})

    monkeypatch.setattr(crm_client.requests, "request", fake_request)
    assert crm_client.push_to_crm(LEAD, score(80)) == "pushed to HubSpot"

    note = calls[-1]
    assert note[1] == "/crm/v3/objects/notes"
    assert note[2]["associations"][0]["to"]["id"] == ("old-7" if existing else "new-1")
    assert "Lead score 80/100" in note[2]["properties"]["hs_note_body"]
    assert all("hs_content_membership_notes" not in str(c[2]) for c in calls)
