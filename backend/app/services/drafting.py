"""Draft generation: short email, LinkedIn note, DM variant.

Hard drafting rules (never invent, never name client/SAP/Wipro internals, never
misstate employment) are enforced here and re-checked by the self-check pass.
"""
from __future__ import annotations

import logging
import re
import textwrap
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import Draft, Lead, Profile
from . import llm

logger = logging.getLogger("outreachhub.drafting")

VARIANT_LABELS = {
    "email": "email",
    "linkedin_note": "LinkedIn connection note",
    "dm": "direct message",
    "proposal": "proposal",
}

DEFAULT_SUBJECT = "Small ask: a few hours a week on {company} + AI work"


@dataclass
class DraftResult:
    variant: str
    channel: str
    subject: str
    body: str
    model: str


def variants_for(lead: Lead) -> list[str]:
    if lead.channel == "email":
        return ["email"]
    return ["linkedin_note", "dm"]


def draft_lead(db: Session, lead: Lead, profile: Profile | None = None) -> list[Draft]:
    profile = profile or db.get(Profile, 1)
    created: list[Draft] = []
    existing = {
        d.variant
        for d in db.query(Draft).filter(
            Draft.lead_id == lead.id, Draft.status.in_(("pending", "approved", "sent"))
        )
    }
    for variant in variants_for(lead):
        if variant in existing:
            continue
        result = _generate(db, lead, profile, variant)
        draft = Draft(
            lead_id=lead.id,
            variant=variant,
            channel=lead.channel,
            subject=result.subject,
            body=result.body,
            status="pending",
            model=result.model,
            generation=1,
        )
        db.add(draft)
        created.append(draft)
    db.commit()
    for draft in created:
        db.refresh(draft)
    if created and lead.status == "enriched":
        lead.status = "drafted"
        db.commit()
    return created


def _generate(db: Session, lead: Lead, profile: Profile, variant: str) -> DraftResult:
    ready, _ = llm.provider_ready()
    if ready:
        try:
            return _generate_with_llm(db, lead, profile, variant)
        except llm.LLMUnavailable:
            pass
    return _generate_fallback(lead, profile, variant)


def _tone(profile: Profile) -> dict:
    return profile.tone or {}


def _generate_with_llm(db: Session, lead: Lead, profile: Profile, variant: str) -> DraftResult:
    tone = _tone(profile)
    max_words = int(tone.get("max_email_words", 120))
    max_chars = int(tone.get("max_linkedin_note_chars", 300))
    limit = max_words if variant == "email" else max_chars

    system = (
        "You write short, honest cold outreach to founders and engineering leaders for one candidate. Reply with JSON only: "
        '{"subject": "...", "body": "..."}\n'
        "Rules (non-negotiable):\n"
        + "\n".join(f"- {r}" for r in tone.get("hard_rules", []))
        + "\n- Tailor specifically as a proactive, agile builder pitching the founder/team on part-time or contract AI engineering.\n"
        "- One specific reference to this company's product/post/repo (use the hook).\n"
        "- Exactly one relevant project of the candidate, chosen from the profile.\n"
        "- Clear ask: a few hours a week, plenty of availability, very eager to learn, "
        "happy to start with a small paid trial task.\n"
        "- Include GitHub (github.com/the-rohit-kumar) and CV link if provided.\n"
        + ("- Polite one-line opt-out.\n" if tone.get("include_opt_out_line", True) else "")
        + f"- Conversational, specific, not salesy, no hype. Style: {tone.get('style', 'conversational')}, "
        f"formality: {tone.get('formality', 'friendly')}."
        + (" No emoji." if not tone.get("emoji") else "")
        + (" No exclamation marks." if not tone.get("exclamation_marks") else "")
        + (
            f"\nLength: email body under {max_words} words."
            if variant == "email"
            else f"\nLength: under {max_chars} characters, plain text, no subject line."
        )
    )
    cv_info = f"\nCandidate CV link: {profile.cv_url}" if getattr(profile, "cv_url", None) and profile.cv_url else ""
    user = (
        f"CANDIDATE:\n{profile.about_me}\n\nSkills: {', '.join(profile.skills or [])}\n"
        f"GitHub: {getattr(profile, 'github_url', None) or 'github.com/the-rohit-kumar'}{cv_info}\n"
        f"Goal: {goal_line(profile)}\n\n"
        f"TARGET:\nCompany: {lead.company}\nRole/post: {lead.title}\n"
        f"Channel: {variant}\nSpecific hook to reference: {lead.hook or lead.title}\n"
        f"Company context: {(lead.enrichment or {}).get('summary', '')}\n\n"
        f"Posting text:\n{(lead.raw_text or lead.description)[:5000]}"
    )

    if variant != "email":
        system += "\nNo subject line; return subject as an empty string."

    data, result = llm.complete_json(
        db,
        system=system,
        user=user,
        purpose="draft",
        model=None,  # strong model
        max_tokens=900,
        temperature=0.6,
    )
    body = str(data.get("body", "")).strip()
    subject = str(data.get("subject", "")).strip()
    if not body:
        raise llm.LLMUnavailable("empty draft from model")
    if not subject and variant == "email":
        subject = DEFAULT_SUBJECT.format(company=lead.company or "your team")
    return DraftResult(variant=variant, channel=lead.channel, subject=subject, body=body, model=result.model)


def goal_line(profile: Profile) -> str:
    text = profile.about_me.lower()
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if "goal:" in sentence.lower() or ("part-time" in sentence.lower() and "remote" in sentence.lower()):
            return sentence.strip()
    return (
        "remote part-time or contract AI/GenAI engineering work (LLM apps, agents, RAG, evals), "
        "ideally USD-paid, to gain real production experience."
    )


def pick_project(profile: Profile, lead: Lead) -> str:
    """Choose the one project of mine that fits the posting (honest, from profile)."""
    text = f"{lead.title} {lead.raw_text} {lead.hook}".lower()
    about = profile.about_me

    doc_markers = ("document", "spec", "design", "sharepoint", "documentation", "automation", "iflow", "integration")
    agent_markers = ("agent", "eval", "evaluation", "rubric", "ragas", "judge", "benchmark", "quality")
    vision_markers = ("vision", "cnn", "image", "video", "opencv", "tensorflow", "keras", "classification")

    if any(m in text for m in doc_markers):
        project = _extract_paragraph(about, ("Work project", "iFlows", "Technical Specification"))
    elif any(m in text for m in agent_markers):
        project = _extract_paragraph(about, ("Self-Improving Agent", "evaluation loop", "LangGraph"))
    elif any(m in text for m in vision_markers):
        project = _extract_paragraph(about, ("Ad Engagement", "multi-task CNN", "OpenCV"))
    else:
        project = _extract_paragraph(about, ("Self-Improving Agent", "Work project"))
    return project


def _extract_paragraph(about: str, markers: tuple[str, ...]) -> str:
    for block in re.split(r"\n\s*\n", about or ""):
        if any(m.lower() in block.lower() for m in markers):
            return " ".join(block.split())
    for line in (about or "").splitlines():
        if any(m.lower() in line.lower() for m in markers):
            return " ".join(line.split())
    return ""


SHORT_PROJECTS = {
    "work": (
        "I built an LLM agent that reads enterprise integration flows and auto-generates "
        "Technical Specification and Technical Design docs, stored in SharePoint"
    ),
    "agent": (
        "I built a self-improving agent with an automated evaluation loop: plan, execute, "
        "evaluate, critique, retry, scored by an LLM-as-judge against a RAGAS-style rubric"
    ),
    "vision": (
        "I built an ad-engagement web app: a multi-task CNN (emotion, age, gender) with "
        "TensorFlow/Keras, OpenCV inference, a Flask API and a React frontend"
    ),
}


def choose_project_key(profile: Profile, lead: Lead) -> str:
    text = f"{lead.title} {lead.raw_text} {lead.hook}".lower()
    about = profile.about_me.lower()
    if any(m in text for m in ("document", "spec", "sharepoint", "documentation", "technical design")) and "work project" in about:
        return "work"
    if any(m in text for m in ("vision", "cnn", "image", "opencv", "tensorflow")) and "ad engagement" in about:
        return "vision"
    return "agent"


def _generate_fallback(lead: Lead, profile: Profile, variant: str) -> DraftResult:
    """Deterministic draft built only from facts in the profile + posting.

    Used when no LLM key is configured. Labelled model='fallback-template'.
    """
    tone = _tone(profile)
    name = _contact_name(lead)
    company = lead.company or "your team"
    hook = (lead.hook or "").strip()
    project_key = choose_project_key(profile, lead)
    project = SHORT_PROJECTS[project_key]
    ask = (
        "I'm looking for part-time or contract AI engineering work - a few hours a week to start, "
        "I have plenty of availability, I'm very eager to learn, and I'm happy to begin with a small "
        "paid trial task."
    )
    opt_out = "If it's not a fit, no worries at all - just say no and I won't follow up." if tone.get(
        "include_opt_out_line", True
    ) else ""

    if variant == "email":
        limit = int(tone.get("max_email_words", 120))
        ask = (
            "I'm after part-time or contract AI work - a few hours a week, plenty of availability, "
            "very eager to learn, happy to start with a small paid trial task."
        )
        opt_out = (
            "If it's not a fit, no worries - just say no and I won't follow up."
            if tone.get("include_opt_out_line", True)
            else ""
        )

        def assemble(hook_clause: str) -> str:
            links = "My GitHub: github.com/the-rohit-kumar"
            if getattr(profile, "cv_url", None) and profile.cv_url:
                links += f" | CV: {profile.cv_url}"
            parts = [
                f"Hi {name},",
                f"I came across {lead.title} at {company}{hook_clause}.",
                f"Quick context: {project}.",
                ask,
                f"{links} - happy to share or do a short call.",
                opt_out,
                f"Thanks, {(profile.display_name or 'Rohit').split()[0]}",
            ]
            text = " ".join(p for p in parts if p).replace(" .", ".").replace("..", ".")
            return textwrap.fill(text, width=1000)  # one flowing block


        subject = DEFAULT_SUBJECT.format(company=company)
        hook_clause = f" - {hook[:120]}" if hook else ""
        body = assemble(hook_clause)
        if len(body.split()) > limit and hook_clause:
            shorter = " ".join(hook.split()[:8])
            body = assemble(f" - {shorter}" if shorter else "")
        if len(body.split()) > limit and hook_clause:
            body = assemble("")
        return DraftResult(variant, "email", subject, body, "fallback-template")

    # LinkedIn note / DM: hard character limit
    core = (
        f"Hi {name} - saw {lead.title} at {company}"
        + (f" ({hook[:90]})" if hook else "")
        + f". I've been building {project[:120]}. "
        + "Looking for part-time/contract AI work - a few hours a week, plenty of availability, "
        "very eager to learn, happy to start with a small paid trial task."
    )
    max_chars = int(tone.get("max_linkedin_note_chars", 300))
    body = core[: max_chars - 1].rstrip() + "…" if len(core) > max_chars else core
    return DraftResult(variant, lead.channel, "", body, "fallback-template")


def _contact_name(lead: Lead) -> str:
    contact = lead.contact or {}
    name = str(contact.get("name") or "").strip()
    if not name or len(name) > 60:
        return "there"
    if name.lower() in ("there", "team"):
        return "there"
    # first name only, when it looks like a person
    if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,40}", name):
        return name.split()[0]
    return "there"
