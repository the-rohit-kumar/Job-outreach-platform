"""Review queue, sending outbox, warm-up, and settings tests."""
from __future__ import annotations

import uuid

from app.models import Draft, Lead, SendEvent, Setting, Suppression, utcnow
from app.services import drafting, sending, warmup
from app.services.leads import upsert_lead


def _seed_draft(db, channel="email", has_email=True) -> tuple[Lead, Draft]:
    uid = uuid.uuid4().hex[:8]
    lead_data = {
        "source": "hn",
        "title": f"AI Engineer (Contract {uid})",
        "company": f"FoundersCo {uid}",
        "url": f"https://foundersco.ai/{uid}",
        "description": "Building next-gen AI agent with LangGraph and Python. Seed funded.",
        "raw_text": "Building next-gen AI agent with LangGraph and Python. Seed funded.",
        "contact": {"name": "Alex", "email": f"alex-{uid}@foundersco.ai" if has_email else ""},
    }
    lead, _ = upsert_lead(db, lead_data)
    lead.channel = channel
    lead.status = "enriched"
    lead.hook = "Building next-gen AI agent with LangGraph and Python"
    db.commit()

    drafts = drafting.draft_lead(db, lead)
    draft = drafts[0]
    return lead, draft



def test_review_queue_empty_when_no_drafts(authed, db):
    # Clear any pending drafts for this test
    db.query(Draft).filter(Draft.status == "pending").delete()
    db.commit()

    res = authed.get("/api/review/next")
    assert res.status_code == 200
    data = res.json()
    assert data["queue_size"] == 0
    assert data["draft"] == {}


def test_review_queue_fetches_next_draft(authed, db):
    lead, draft = _seed_draft(db, channel="email")

    res = authed.get("/api/review/next")
    assert res.status_code == 200
    data = res.json()
    assert data["queue_size"] >= 1
    assert data["draft"]["id"] == draft.id
    assert data["lead"]["company"].startswith("FoundersCo")
    assert data["draft"]["subject"]


def test_review_action_edit(authed, db):
    lead, draft = _seed_draft(db, channel="email")

    new_body = (
        "Hi Alex, I came across your post at FoundersCo. "
        "Quick context: I built a self-improving agent with an automated evaluation loop in LangGraph. "
        "I have a few hours a week available, very eager to learn, and happy to start with a small paid trial task. "
        "My GitHub: github.com/the-rohit-kumar. If it's not a fit, no worries - just say no and I won't follow up. "
        "Thanks, Rohit"
    )
    res = authed.post(
        f"/api/review/{draft.id}/action",
        json={"action": "edit", "body": new_body, "subject": "Quick AI question for FoundersCo"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["checks_ok"] is True

    db.refresh(draft)
    assert draft.body == new_body
    assert draft.subject == "Quick AI question for FoundersCo"


def test_review_action_approve_email_queues_outbox(authed, db):
    lead, draft = _seed_draft(db, channel="email", has_email=True)
    body = (
        f"Hi Alex, I came across what you are building at {lead.company} - unique AI eval loop with custom benchmarks. "
        "Quick context: I built an LLM agent that reads enterprise integration flows and auto-generates docs. "
        "I have a few hours a week, very eager to learn, happy to start with a small paid trial task. "
        "My GitHub: github.com/the-rohit-kumar. If it is not a fit, no worries - just say no. Thanks, Rohit"
    )

    res = authed.post(
        f"/api/review/{draft.id}/action",
        json={"action": "approve", "body": body},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["queued"] is True
    assert "send_event_id" in data

    db.refresh(draft)
    assert draft.status == "approved"

    event = db.get(SendEvent, data["send_event_id"])
    assert event is not None
    assert event.channel == "email"
    assert event.recipient == (lead.contact or {}).get("email")
    assert event.status == "queued"


def test_review_action_skip(authed, db):
    lead, draft = _seed_draft(db, channel="platform")

    res = authed.post(
        f"/api/review/{draft.id}/action",
        json={"action": "skip"},
    )
    assert res.status_code == 200
    db.refresh(draft)
    assert draft.status == "skipped"


def test_review_action_never_contact_suppresses_lead(authed, db):
    lead, draft = _seed_draft(db, channel="email")

    res = authed.post(
        f"/api/review/{draft.id}/action",
        json={"action": "never_contact"},
    )
    assert res.status_code == 200
    db.refresh(draft)
    assert draft.status == "rejected"

    db.refresh(lead)
    assert lead.opted_out is True
    assert lead.status == "suppressed"

    # Check suppression table
    suppressed = db.query(Suppression).filter(Suppression.kind == "person", Suppression.value == "alex").first()
    assert suppressed is not None




def test_review_stats(authed, db):
    res = authed.get("/api/review/stats")
    assert res.status_code == 200
    data = res.json()
    assert "pending" in data
    assert "needs_manual" in data
    assert "reviewed_today" in data


def test_settings_read_and_update(authed):
    res = authed.get("/api/settings")
    assert res.status_code == 200
    data = res.json()
    assert "settings" in data
    assert "warmup" in data

    update_res = authed.put(
        "/api/settings",
        json={"values": {"daily.target_sent": 40, "send.spacing_minutes_min": 4}},
    )
    assert update_res.status_code == 200

    check_res = authed.get("/api/settings")
    assert check_res.json()["raw"]["daily.target_sent"] == 40
    assert check_res.json()["raw"]["send.spacing_minutes_min"] == 4



def test_warmup_caps_calculation(db):
    assert warmup.ramp_email_cap(1) == 10
    assert warmup.ramp_email_cap(3) == 10
    assert warmup.ramp_email_cap(5) == 20
    assert warmup.ramp_email_cap(10) == 30
    assert warmup.ramp_email_cap(20) == 50

    assert warmup.ramp_platform_cap(2) == 5
    assert warmup.ramp_platform_cap(6) == 10
    assert warmup.ramp_platform_cap(15) == 25


def test_gmail_status_endpoint(authed):
    res = authed.get("/api/gmail/status")
    assert res.status_code == 200
    data = res.json()
    assert "connected" in data
    assert "address" in data
