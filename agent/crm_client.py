"""Where qualified leads go. Uses the real HubSpot API if a token is set,
otherwise writes to a local CSV so the whole pipeline still runs and
produces something you can open and look at with zero CRM account.
"""

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
LOCAL_CRM_FILE = OUTPUT_DIR / "crm_leads.csv"
LOCAL_CRM_FIELDS = ["name", "email", "company", "score", "reasoning"]

HUBSPOT_API = "https://api.hubapi.com"
NOTE_TO_CONTACT = 202  # HubSpot's built-in association type id for note -> contact


def _hubspot_configured() -> bool:
    return bool(os.getenv("HUBSPOT_ACCESS_TOKEN"))


def _hubspot(method: str, path: str, **kwargs) -> requests.Response:
    headers = {"Authorization": f"Bearer {os.environ['HUBSPOT_ACCESS_TOKEN']}"}
    return requests.request(method, f"{HUBSPOT_API}{path}", headers=headers, timeout=15, **kwargs)


def _find_contact_id(email: str) -> str | None:
    search = {"filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}], "limit": 1}
    response = _hubspot("POST", "/crm/v3/objects/contacts/search", json=search)
    response.raise_for_status()
    results = response.json().get("results", [])
    return results[0]["id"] if results else None


def _upsert_contact(lead: dict) -> str:
    """Create the contact, or reuse the existing one if this email is
    already in HubSpot (which answers 409 on a duplicate create)."""
    name_parts = lead["name"].split(" ")
    properties = {
        "email": lead["email"],
        "firstname": name_parts[0],
        "lastname": " ".join(name_parts[1:]),
        "company": lead["company"],
    }
    response = _hubspot("POST", "/crm/v3/objects/contacts", json={"properties": properties})
    if response.status_code == 409:
        contact_id = _find_contact_id(lead["email"])
        if contact_id:
            return contact_id
    response.raise_for_status()
    return response.json()["id"]


def _add_note(contact_id: str, body: str) -> None:
    payload = {
        "properties": {
            "hs_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "hs_note_body": body,
        },
        "associations": [{
            "to": {"id": contact_id},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": NOTE_TO_CONTACT}],
        }],
    }
    response = _hubspot("POST", "/crm/v3/objects/notes", json=payload)
    response.raise_for_status()


def push_to_crm(lead: dict, score) -> str:
    """Send a qualified lead to the CRM. score is a LeadScore instance.

    Note on HubSpot: firstname, lastname, email and company are standard
    contact properties, but the score and reasoning are not. Rather than
    require every client to create custom properties before this works at
    all, they're attached to the contact as a note, which shows up on the
    contact's timeline. If a client does want them as real filterable
    properties, create them in HubSpot under Settings > Properties and add
    them to the contact properties in _upsert_contact.
    """
    if _hubspot_configured():
        contact_id = _upsert_contact(lead)
        _add_note(contact_id, f"Lead score {score.score}/100. {score.reasoning}")
        return "pushed to HubSpot"

    # Local mock CRM: one row per email, so re-running the batch updates
    # leads instead of duplicating them.
    OUTPUT_DIR.mkdir(exist_ok=True)
    rows = {}
    if LOCAL_CRM_FILE.exists():
        with open(LOCAL_CRM_FILE, "r", encoding="utf-8", newline="") as f:
            rows = {row["email"]: row for row in csv.DictReader(f)}
    rows[lead["email"]] = {
        "name": lead["name"], "email": lead["email"], "company": lead["company"],
        "score": score.score, "reasoning": score.reasoning,
    }
    with open(LOCAL_CRM_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOCAL_CRM_FIELDS)
        writer.writeheader()
        writer.writerows(rows.values())
    return f"saved to {LOCAL_CRM_FILE.name} (mock CRM)"


def notify_slack(lead: dict, score) -> str | None:
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return None

    message = (
        f"New qualified lead: {lead['name']} at {lead['company']} "
        f"(score {score.score}/100)\n{score.reasoning}"
    )
    try:
        response = requests.post(webhook_url, json={"text": message}, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        return f"Slack alert failed: {exc}"
    return "posted to Slack"
