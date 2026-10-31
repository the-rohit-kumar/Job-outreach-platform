"""Scoring: keyword prefilter, then LLM score 0-100 against the profile.

Without an API key a deterministic heuristic scores the lead and the result is
labelled ``model=heuristic`` so nothing pretends to be an LLM judgement.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import Lead, Profile, Setting
from . import llm

DEFAULT_KEYWORDS = [
    "llm", "langchain", "langgraph", "rag", "genai", "generative ai", "agent", "ai engineer",
    "machine learning", "python", "nlp", "prompt", "vector", "evaluation", "evals", "mcp",
    "part-time", "part time", "contract", "freelance", "remote", "hourly", "trial task",
    "junior", "entry level", "entry-level", "0-2 years", "1-2 years", "associate", "early career",
]

NEGATIVE_KEYWORDS = [
    "senior director", "vp of", "chief architect", "10+ years", "12+ years", "8+ years", "7+ years",
    "6+ years", "5+ years", "4+ years", "3+ years", "5-7 years", "3-5 years", "5+ yrs", "3+ yrs",
    "senior engineer", "staff engineer", "principal engineer", "lead engineer",
    "onsite only", "cleared personnel", "security clearance", "w2 only", "no agencies",
    "office manager", "people ops", "recruiter", "account executive", "sales development",
]

HIGH_YOE_PATTERNS = [
    re.compile(r"\b([3-9]|\d{2,})\+?\s*(?:-\s*\d+)?\s*(?:years?|yrs?)(?:\s+of)?(?:\s+experience|\s+exp)?\b", re.I),
    re.compile(r"\b(?:minimum|at least|more than)\s+([3-9]|\d{2,})\s*(?:years?|yrs?)\b", re.I),
    re.compile(r"\b([3-9]|\d{2,})\s*to\s*\d+\s*(?:years?|yrs?)\b", re.I),
]

TARGET_YOE_PATTERNS = [
    re.compile(r"\b(?:0\s*-\s*[12]|1\s*-\s*2|[012])\+?\s*(?:years?|yrs?)(?:\s+of)?(?:\s+experience|\s+exp)?\b", re.I),
    re.compile(r"\b(junior|jr\.?|entry[\s-]level|associate|fresher|graduate|new grad|intern|early[\s-]career|0-2\s*yoe|1-2\s*yoe)\b", re.I),
]

SENIOR_TITLE_WORDS = ("senior", "sr.", "sr ", "staff", "principal", "lead", "architect", "director", "head of", "vp")

STARTUP_SIGNALS = [
    "seed", "pre-seed", "series a", "backed by", "y combinator", "yc", "we are a team",
    "early stage", "stealth", "bootstrapped", "solo founder",
]

FOUNDER_SIGNALS = [
    "founder", "co-founder", "founding engineer", "first engineer", "early engineer",
    "seed", "pre-seed", "stealth", "yc", "y combinator", "bootstrap", "solo founder",
    "dm me", "email me directly", "reach out to me", "building in public", "show hn", "launch hn",
]



@dataclass
class ScoreResult:
    score: int
    reason: str
    model: str
    qualified: bool


def threshold(db: Session) -> int:
    row = db.get(Setting, "scoring.threshold")
    try:
        return int(row.value) if row and row.value is not None else 60
    except (TypeError, ValueError):
        return 60


def _setting(db: Session, key: str, default):
    row = db.get(Setting, key)
    return default if row is None or row.value is None else row.value


def prefilter(lead: Lead, keywords: list[str] | None = None) -> bool:
    """Cheap keyword gate before any LLM call."""
    text = f"{lead.title} {lead.description} {lead.raw_text}".lower()
    # Reject non-technical roles that only matched due to 'remote'
    if any(dq in text for dq in ("office manager", "people ops", "recruiter", "account executive")):
        return False
    keywords = keywords if keywords is not None else list(_default_keywords())
    return any(k.lower() in text for k in keywords)



def _default_keywords() -> list[str]:
    from ..seed import DEFAULT_SKILLS

    words = list(DEFAULT_KEYWORDS)
    words.extend(s.lower() for s in DEFAULT_SKILLS if len(s) > 3)
    return words


def score_lead(db: Session, lead: Lead, profile: Profile | None = None) -> ScoreResult:
    profile = profile or db.get(Profile, 1)
    profile_text = _profile_text(profile)

    # 1) LLM path
    ready, _ = llm.provider_ready()
    if ready:
        try:
            return _score_with_llm(db, lead, profile_text)
        except llm.LLMUnavailable:
            pass  # fall through to heuristic

    # 2) Deterministic fallback
    score, reason = heuristic_score(lead, profile)
    is_disqualified = "senior/lead title" in reason or ">2 YOE" in reason
    result = ScoreResult(
        score=score,
        reason=reason,
        model="heuristic-fallback",
        qualified=(score >= threshold(db)) and not is_disqualified,
    )
    _persist(db, lead, result)
    return result


def _profile_text(profile: Profile | None) -> str:
    if profile is None:
        return ""
    return "\n".join(
        [
            profile.about_me,
            "Skills: " + ", ".join(profile.skills or []),
            "Location: " + (profile.location or ""),
        ]
    ).strip()


def _score_with_llm(db: Session, lead: Lead, profile_text: str) -> ScoreResult:
    system = (
        "You score job/posting leads for one candidate with 0-2 years of experience. Reply with strict JSON only: "
        '{"score": <0-100 integer>, "reason": "<one line, max 120 chars>"}\n'
        "Scoring criteria:\n"
        "1. Experience constraint (CRITICAL - 0-2 YEARS RADIUS): Candidate has ~1 year of experience (0-2 years bracket). "
        "Award top scores (80-100) to roles asking for 0-2 years, junior, entry-level, associate, or early-stage startup roles without strict senior YOE. "
        "Heavily penalize or disqualify (score < 40) any role requiring 3+ years of experience, or with Senior, Staff, Principal, Lead, Architect in title.\n"
        "2. Tech fit: Relevance to Python, GenAI, LangChain, LangGraph, agents, RAG, LLM evals, backend.\n"
        "3. Working model: Remote-friendly; part-time / contract / freelance / trial task friendly.\n"
        "4. Timezone/Pay: IST overlap and USD pay are pluses."
    )
    user = (
        f"CANDIDATE PROFILE:\n{profile_text}\n\n"
        f"LEAD:\nTitle: {lead.title}\nCompany: {lead.company}\n"
        f"Location: {lead.location}\nType: {lead.employment_type}\nRemote: {lead.remote}\n\n"
        f"Posting:\n{(lead.raw_text or lead.description)[:6000]}"
    )
    data, result = llm.complete_json(
        db,
        system=system,
        user=user,
        purpose="score",
        model=settings_fast_model(),
        max_tokens=300,
        temperature=0.0,
    )
    score = _clamp(data.get("score", 0))
    reason = str(data.get("reason", ""))[:512]
    out = ScoreResult(
        score=score,
        reason=reason or "scored by LLM",
        model=result.model,
        qualified=score >= threshold(db),
    )
    _persist(db, lead, out)
    return out


def settings_fast_model() -> str:
    from ..config import settings

    return settings.llm_fast_model


def _clamp(value) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


def heuristic_score(lead: Lead, profile: Profile | None) -> tuple[int, str]:
    text = f"{lead.title} {lead.description} {lead.raw_text}".lower()
    title_lower = (lead.title or "").lower()
    signals: list[str] = []
    score = 30

    skills = [s.lower() for s in (profile.skills if profile else [])] or _default_keywords()
    matched = sorted({s for s in skills if len(s) > 3 and s in text})[:8]
    if matched:
        score += min(30, 4 * len(matched))
        signals.append(f"skills: {', '.join(matched[:4])}")

    # Founder and Early-Stage Boost (ideal for direct outreach)
    founder_hits = [f for f in FOUNDER_SIGNALS if f in text or f in title_lower]
    if founder_hits:
        score += 20
        signals.append(f"founder signal: {founder_hits[0]}")
    elif any(k in text for k in STARTUP_SIGNALS):
        score += 10
        signals.append("small team signal")

    if lead.remote or "remote" in text or "anywhere" in text:
        score += 10
        signals.append("remote")
    if any(k in text for k in ("part-time", "part time", "contract", "freelance", "hourly", "trial task")):
        score += 15
        signals.append("part-time/contract")
    if re.search(r"\b(india|ist|utc\+?5|flexible hours|overlap)\b", text):
        score += 5
        signals.append("timezone overlap")

    # Penalize Heavy Senior / Enterprise requirements & High YOE (strict 0-2 years radius)
    disqualified_senior = False
    if any(s in title_lower for s in SENIOR_TITLE_WORDS):
        score -= 35
        signals.append("senior/lead title (>2 YOE)")
        disqualified_senior = True

    high_yoe_hit = None
    for pat in HIGH_YOE_PATTERNS:
        m = pat.search(text)
        if m:
            high_yoe_hit = m.group(0)
            break

    if high_yoe_hit:
        score -= 35
        signals.append(f"requires {high_yoe_hit} (>2 YOE)")
        disqualified_senior = True

    # Boost explicit 0-2 years / junior / early career roles
    if not disqualified_senior:
        target_yoe_hit = None
        for pat in TARGET_YOE_PATTERNS:
            m = pat.search(f"{title_lower} {text}")
            if m:
                target_yoe_hit = m.group(0)
                break
        if target_yoe_hit:
            score += 20
            signals.append(f"0-2 YOE fit: {target_yoe_hit}")

    negatives = [k for k in NEGATIVE_KEYWORDS if k in text]
    if negatives:
        score -= 20
        signals.append(f"minus: {negatives[0]}")

    if not any(k in text for k in ("python", "llm", "ai", "ml", "rag", "agent", "backend", "nlp", "langchain", "langgraph")):
        score -= 25
        signals.append("weak stack overlap")

    if disqualified_senior:
        # Cap score so roles requiring >2 YOE never qualify when threshold is 60
        score = min(score, 45)

    score = max(0, min(100, score))
    reason = "; ".join(signals)[:512] or "no strong signals"
    return score, reason



def _persist(db: Session, lead: Lead, result: ScoreResult) -> None:
    lead.score = result.score
    lead.score_reason = result.reason
    lead.score_model = result.model
    if lead.status in ("new", "prefiltered"):
        lead.status = "qualified" if result.qualified else "filtered"
    db.commit()


def score_new_leads(db: Session) -> dict:
    profile = db.get(Profile, 1)
    pending = (
        db.query(Lead)
        .filter(Lead.status == "new", Lead.duplicate_of.is_(None))
        .limit(500)
        .all()
    )
    prefiltered = scored = qualified = 0
    for lead in pending:
        if not prefilter(lead):
            lead.status = "prefiltered"
            prefiltered += 1
            db.commit()
            continue
        result = score_lead(db, lead, profile)
        scored += 1
        if result.qualified:
            qualified += 1
    return {
        "candidates": len(pending),
        "prefiltered": prefiltered,
        "scored": scored,
        "qualified": qualified,
    }
