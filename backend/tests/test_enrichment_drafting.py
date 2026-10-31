"""Enrichment, drafting and self-check tests (all offline)."""
from __future__ import annotations

import uuid

from app.models import Draft, Lead, Profile
from app.services import drafting, enrichment, self_check
from app.services.leads import upsert_lead

from .conftest import fixture_text, make_transport


def _qualified_lead(db, **overrides) -> Lead:
    data = {
        "source": "manual",
        "title": "Part-time LLM engineer (RAG + evals)",
        "company": "Pixie Labs",
        "url": f"https://pixielabs.ai/careers/llm-{uuid.uuid4().hex[:8]}",
        "description": "We are a small team building an AI support agent. Contract, remote, Python.",
        "raw_text": "We are a small team building an AI support agent. Contract, remote, Python.",
        "remote": True,
    }
    lead, _ = upsert_lead(db, data)
    lead.status = "qualified"
    if "channel" in overrides:
        lead.channel = overrides["channel"]
    if "company" in overrides:
        lead.company = overrides["company"]
    if "url" in overrides:
        lead.url = overrides["url"]
    db.commit()
    return lead


# --- enrichment -------------------------------------------------------------
def test_enrichment_finds_public_email_and_hook(db):
    lead = _qualified_lead(db)
    transport = make_transport({"pixielabs.ai": (200, fixture_text("company_page.html"))})
    result = enrichment.enrich_lead(db, lead, transport=transport)
    assert result.public_email == "hello@pixielabs.ai"
    assert result.channel == "email"
    assert lead.channel == "email"
    assert lead.contact["email"] == "hello@pixielabs.ai"
    assert "python" in result.stack
    assert "team of 8" in result.team_size_hint
    assert result.hook and len(result.hook) > 20


def test_enrichment_without_public_email_routes_to_platform(db):
    lead = _qualified_lead(db, url="https://news.ycombinator.com/item?id=1", company="HN Startup")
    result = enrichment.enrich_lead(db, lead, transport=make_transport({}))
    assert result.public_email == ""
    assert result.channel == "platform"
    assert lead.channel == "platform"
    assert lead.hook


# --- drafting ---------------------------------------------------------------
def test_fallback_email_draft_follows_hard_rules(db):
    lead = _qualified_lead(db, channel="email")
    profile = db.get(Profile, 1)
    drafts = drafting.draft_lead(db, lead, profile)
    email = next(d for d in drafts if d.variant == "email")
    body = email.body.lower()
    assert len(email.body.split()) <= 150
    assert "sap" not in body
    assert "pixie labs" in body
    assert "few hours a week" in body
    assert "trial task" in body
    assert "not a fit" in body or "no worries" in body  # opt-out
    assert "github.com/the-rohit-kumar" in email.body
    assert email.model == "fallback-template"


def test_platform_channel_creates_short_variants(db):
    lead = _qualified_lead(db, channel="platform")
    drafts = drafting.draft_lead(db, lead, db.get(Profile, 1))
    variants = {d.variant for d in drafts}
    assert variants == {"linkedin_note", "dm"}
    for draft in drafts:
        assert len(draft.body) <= 300


def test_draft_not_recreated_for_existing_pending(db):
    lead = _qualified_lead(db, channel="platform")
    drafting.draft_lead(db, lead, db.get(Profile, 1))
    again = drafting.draft_lead(db, lead, db.get(Profile, 1))
    assert again == []


# --- self-check -------------------------------------------------------------
def test_self_check_passes_good_fallback_draft(db):
    lead = _qualified_lead(db, channel="email")
    profile = db.get(Profile, 1)
    drafts = drafting.draft_lead(db, lead, profile)
    draft = next(d for d in drafts if d.variant == "email")
    result = self_check.check_draft(db, draft, lead, profile, recent_bodies=[])
    assert result.ok, result.reasons
    assert result.checks["hook_ok"] is True
    assert result.checks["ask_ok"] is True


def test_self_check_rejects_forbidden_mentions(db):
    lead = _qualified_lead(db, channel="email")
    profile = db.get(Profile, 1)
    draft = Draft(
        lead_id=lead.id,
        variant="email",
        channel="email",
        subject="Hello",
        body=(
            "Hi there, I worked on SAP systems for a client and increased output by 40% while "
            "saving $2M. I am excited to apply and I believe I would be a great fit. "
            "I have availability, few hours a week, trial task possible, or say no if not a fit."
        ),
        status="pending",
    )
    db.add(draft)
    db.commit()
    result = self_check.check_draft(db, draft, lead, profile, recent_bodies=[])
    assert result.ok is False
    joined = " ".join(result.reasons)
    assert "SAP" in joined or "forbidden" in joined
    assert "claim" in joined
    assert "generic" in joined


def test_self_check_rejects_repetition(db):
    lead = _qualified_lead(db, channel="email")
    profile = db.get(Profile, 1)
    drafts = drafting.draft_lead(db, lead, profile)
    draft = next(d for d in drafts if d.variant == "email")
    result = self_check.check_draft(db, draft, lead, profile, recent_bodies=[draft.body])
    assert result.ok is False
    assert any("similar" in r or "reuses" in r for r in result.reasons)


def test_self_check_marks_needs_manual_after_two_failures(db, monkeypatch):
    lead = _qualified_lead(db, channel="email")
    profile = db.get(Profile, 1)
    drafts = drafting.draft_lead(db, lead, profile)
    draft = next(d for d in drafts if d.variant == "email")
    # Isolate: drop every other pending draft so only this one is checked.
    db.query(Draft).filter(Draft.status == "pending", Draft.id != draft.id).delete()
    draft.body = "SAP SAP no ask and no hook at all here"
    draft.generation = 2  # regeneration attempts exhausted -> failure is final
    db.commit()

    result = self_check.run_self_check(db)
    db.refresh(draft)
    assert draft.status == "needs_manual"
    assert result["needs_manual"] >= 1


def test_self_check_regeneration_can_recover(db, monkeypatch):
    lead = _qualified_lead(db, channel="email")
    profile = db.get(Profile, 1)
    drafts = drafting.draft_lead(db, lead, profile)
    draft = next(d for d in drafts if d.variant == "email")
    db.query(Draft).filter(Draft.status == "pending", Draft.id != draft.id).delete()
    draft.body = "SAP junk that will fail every check"
    draft.generation = 0
    db.commit()

    monkeypatch.setattr(
        drafting,
        "_generate",
        lambda *a, **k: drafting.DraftResult(
            "email",
            "email",
            "Small ask",
            (
                "Hi there, I came across your role at Pixie Labs. I built a self-improving "
                "agent with an evaluation loop. I'm looking for part-time work - a few hours "
                "a week, plenty of availability, happy to start with a small paid trial task. "
                "If it's not a fit, no worries - just say no. Thanks, Rohit"
            ),
            "test",
        ),
    )
    result = self_check.run_self_check(db)
    db.refresh(draft)
    assert result["regenerated"] >= 1
    assert draft.status == "pending"
