"""First-run seed data: default profile, onboarding checklist, base settings."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import OnboardingItem, Profile, Setting

DEFAULT_ABOUT_ME = """Rohit Kumar — software engineer at Wipro Technologies, Bengaluru, working on GenAI,
Python, and automation. BTech in CSE from VIT Chennai (2025).

Work project: built an LLM agent that reads enterprise integration flows (iFlows) and automatically
generates Technical Specification and Technical Design documents, then stores them directly in the
client's SharePoint.

Personal project: Self-Improving Agent with Automated Evaluation Loop — an autonomous agent that
attempts a task, scores its own output with an independent LLM-as-judge against a RAGAS-style
rubric (relevance, correctness, completeness), critiques it, and retries until it clears a quality
threshold. Built with LangGraph and LangChain (plan -> execute -> evaluate -> critique -> retry),
with failure-mode logging that tracks quality gains across iterations.

Personal project: Ad Engagement Analysis web app — multi-task CNN (emotion, age, gender) using
transfer learning, TensorFlow/Keras, real-time inference with OpenCV, Flask REST API, React frontend.

Skills: Python, LangChain, LangGraph, agentic AI (ReAct), RAG pipelines, vector databases (FAISS,
ChromaDB), prompt engineering, LLM evaluation, document automation, REST APIs, SharePoint
integration, SQL, Node.js, Git, ML/DL (TensorFlow, Keras, NumPy, Pandas). Uses Claude Code daily.

AWS Certified Cloud Practitioner. LeetCode rating 1436. GitHub: github.com/the-rohit-kumar

Goal: remote part-time or contract AI/GenAI engineering work (LLM apps, agents, RAG, evals),
ideally USD-paid, to gain real production experience. Has a lot of time to put in and is very
eager to learn. Happy to start with a small paid trial task."""

DEFAULT_SKILLS = [
    "Python",
    "LangChain",
    "LangGraph",
    "agentic AI (ReAct)",
    "RAG pipelines",
    "FAISS",
    "ChromaDB",
    "prompt engineering",
    "LLM evaluation",
    "document automation",
    "REST APIs",
    "SharePoint integration",
    "SQL",
    "Node.js",
    "Git",
    "TensorFlow",
    "Keras",
    "NumPy",
    "Pandas",
    "Claude Code",
]

DEFAULT_DO_NOT_MENTION = [
    "Client names",
    "Wipro-internal details",
    "SAP",
]

DEFAULT_TONE = {
    "style": "conversational",
    "formality": "friendly",
    "max_email_words": 120,
    "max_linkedin_note_chars": 300,
    "include_opt_out_line": True,
    "emoji": False,
    "exclamation_marks": False,
    "hard_rules": [
        "Never name the client or any Wipro-internal details.",
        "Describe the work project only as written in the About me block.",
        "Never invent metrics, tools, results, titles, or employers.",
        "Never claim to be unemployed or misstate work status.",
        "Do not mention SAP.",
    ],
}

ONBOARDING_ITEMS = [
    ("profile", "Profile done (About me + do-not-mention list filled in)", "/profile", 1, True),
    ("gmail", "Gmail connected (Google sign-in, OAuth only)", "/settings", 2, False),
    ("sources", "Sources enabled (API collectors turned on)", "/sources", 3, False),
    ("extension", "Chrome extension installed (token pasted)", "/help", 4, True),
    ("first_review", "First review session completed", "/review", 5, False),
]

DEFAULT_SETTINGS: dict[str, object] = {
    "daily.target_collected": 300,
    "daily.target_qualified": 100,
    "daily.target_drafts": 50,
    "daily.target_sent": 35,
    "warmup.email_daily_cap": 10,
    "warmup.platform_daily_cap": 10,
    "send.window_start": "09:00",
    "send.window_end": "18:00",
    "send.spacing_minutes_min": 3,
    "send.spacing_minutes_max": 8,
    "send.pause_bounce_rate": 0.05,
    "gmail.connected": False,
    "gmail.address": "",
}


def seed(db: Session) -> None:
    """Idempotent first-run seed."""
    if db.get(Profile, 1) is None:
        db.add(
            Profile(
                id=1,
                display_name="Rohit Kumar",
                email="",
                location="Bengaluru, India (IST)",
                about_me=DEFAULT_ABOUT_ME,
                skills=DEFAULT_SKILLS,
                do_not_mention=DEFAULT_DO_NOT_MENTION,
                tone=DEFAULT_TONE,
            )
        )

    for key, label, href, order, auto in ONBOARDING_ITEMS:
        existing = db.get(OnboardingItem, key)
        if existing is None:
            db.add(
                OnboardingItem(
                    key=key, label=label, href=href, order_index=order, auto=auto, done=False
                )
            )
        elif existing.auto != auto:
            existing.auto = auto
            existing.label = label
            existing.href = href
            existing.order_index = order

    for key, value in DEFAULT_SETTINGS.items():
        if db.get(Setting, key) is None:
            db.add(Setting(key=key, value=value))

    db.commit()
