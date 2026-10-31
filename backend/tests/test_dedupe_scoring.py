"""Dedupe and scoring tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import Lead, Setting, utcnow
from app.services import dedupe, scoring
from app.services.leads import upsert_lead


def _lead(db, **kwargs):
    data = {
        "source": "manual",
        "title": "Python LLM engineer",
        "company": "Acme",
        "url": kwargs.pop("url", ""),
        "description": "part-time contract building RAG agents with Python and LangChain",
        "raw_text": "part-time contract building RAG agents with Python and LangChain",
        **kwargs,
    }
    lead, _ = upsert_lead(db, data)
    return lead


# --- dedupe -----------------------------------------------------------------
def test_upsert_dedupes_by_url(db):
    lead1, outcome1 = upsert_lead(db, {"source": "a", "title": "Role", "company": "X", "url": "https://x.com/j/1"})
    lead2, outcome2 = upsert_lead(db, {"source": "b", "title": "Role", "company": "X", "url": "https://x.com/j/1/"})
    assert outcome1 == "created"
    assert outcome2 == "duplicate"
    assert lead2.id == lead1.id


def test_fuzzy_dedupe_marks_similar_titles(db):
    a = _lead(db, url="https://a.com/1", title="Senior ML Engineer", company="DataWorks")
    b = _lead(db, url="https://b.com/2", title="Senior ML Engineer", company="DataWorks")
    assert a.id != b.id
    result = dedupe.run_dedupe(db)
    assert result["marked_duplicate"] >= 1
    db.refresh(b)
    assert b.status == "duplicate"
    assert b.duplicate_of == a.id


def test_company_cooldown(db):
    contacted = _lead(db, url="https://cool.com/1", company="CoolCo")
    contacted.contacted_at = utcnow()
    db.commit()
    fresh = _lead(db, url="https://cool.com/2", company="CoolCo")
    dedupe.apply_company_cooldown(db)
    db.refresh(fresh)
    assert fresh.status == "cooldown"


def test_cooldown_window_is_configurable(db):
    row = db.get(Setting, "dedupe.cooldown_days")
    if row is None:
        db.add(Setting(key="dedupe.cooldown_days", value=0))
    else:
        row.value = 0
    db.commit()
    contacted = _lead(db, url="https://old.com/1", company="OldCo")
    contacted.contacted_at = utcnow() - timedelta(days=1)
    db.commit()
    fresh = _lead(db, url="https://old.com/2", company="OldCo")
    dedupe.apply_company_cooldown(db)
    db.refresh(fresh)
    assert fresh.status != "cooldown"


# --- scoring ----------------------------------------------------------------
def test_prefilter_rejects_off_topic(db):
    lead = _lead(db, url="https://seo.com/1", title="SEO Manager", company="GrowthCo",
                 description="Search engine optimisation for retail", raw_text="Search engine optimisation")
    assert scoring.prefilter(lead) is False


def test_prefilter_accepts_ai_role(db):
    lead = _lead(db, url="https://ai.com/1", title="Python LLM engineer")
    assert scoring.prefilter(lead) is True


def test_heuristic_scores_relevant_lead_high(db):
    lead = _lead(
        db,
        url="https://good.com/1",
        title="Part-time LLM engineer (RAG)",
        description="Contract role, remote, Python, LangChain agents, few hours a week",
        raw_text="Contract role, remote, Python, LangChain agents, few hours a week",
        remote=True,
    )
    result = scoring.score_lead(db, lead)
    assert result.score >= 60
    assert result.qualified is True
    assert result.model == "heuristic-fallback"
    db.refresh(lead)
    assert lead.status == "qualified"
    assert lead.score_reason


def test_heuristic_scores_irrelevant_lead_low(db):
    lead = _lead(
        db,
        url="https://bad.com/1",
        title="Onsite Java J2EE Lead, 12+ years, W2 only",
        description="Enterprise SOAP web services, 12+ years experience required, onsite only",
        raw_text="Enterprise SOAP web services, 12+ years experience required, onsite only",
        remote=False,
    )
    result = scoring.score_lead(db, lead)
    assert result.score < 60
    assert result.qualified is False
    db.refresh(lead)
    assert lead.status == "filtered"


def test_score_threshold_is_configurable(db):
    row = db.get(Setting, "scoring.threshold")
    if row is None:
        row = Setting(key="scoring.threshold", value=10)
        db.add(row)
    else:
        row.value = 10
    db.commit()
    lead = _lead(db, url="https://meh.com/1", title="Something Python-ish", remote=True)
    result = scoring.score_lead(db, lead)
    assert result.qualified is True
    # Restore standard threshold
    row.value = 60
    db.commit()


def test_heuristic_penalizes_senior_and_high_yoe(db):
    # Senior title
    senior_lead = _lead(
        db,
        url="https://senior.com/1",
        title="Senior AI Engineer (RAG/LangChain)",
        description="Remote contract Python role building agents",
        remote=True,
    )
    result = scoring.score_lead(db, senior_lead)
    assert result.score <= 45
    assert result.qualified is False
    assert "senior/lead title" in result.reason

    # High YOE requirement (e.g. 5+ years)
    high_yoe_lead = _lead(
        db,
        url="https://highyoe.com/1",
        title="AI Engineer",
        description="Requires 5+ years of experience in ML/AI systems",
        raw_text="Requires 5+ years of experience in ML/AI systems. Remote contract Python.",
        remote=True,
    )
    result2 = scoring.score_lead(db, high_yoe_lead)
    assert result2.score <= 45
    assert result2.qualified is False
    assert ">2 YOE" in result2.reason


def test_heuristic_boosts_0_to_2_yoe(db):
    junior_lead = _lead(
        db,
        url="https://junior.com/1",
        title="Junior AI Engineer (0-2 years)",
        description="Looking for entry-level or junior engineer with 0-2 years experience in Python and LangChain",
        raw_text="Looking for entry-level or junior engineer with 0-2 years experience in Python and LangChain. Remote trial task.",
        remote=True,
    )
    result = scoring.score_lead(db, junior_lead)
    assert result.score >= 60
    assert result.qualified is True
    assert "0-2 YOE fit" in result.reason
