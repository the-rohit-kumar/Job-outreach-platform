"""Resume parsing and automatic search filter synchronization.

Extracts text from uploaded PDF/text resumes, extracts candidate skills,
experience and projects, updates Profile (about_me and skills), and
automatically syncs search keywords to all active collectors.
"""
from __future__ import annotations

import io
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from ..models import Collector, Profile, Setting, utcnow
from . import llm

logger = logging.getLogger("outreachhub.resume")

TECH_DICTIONARY = [
    "Python", "LangChain", "LangGraph", "FastAPI", "React", "TypeScript", "JavaScript",
    "TensorFlow", "PyTorch", "Keras", "Docker", "PostgreSQL", "SQLite", "SQL", "Git",
    "ChromaDB", "FAISS", "Pinecone", "Weaviate", "Qdrant", "RAG", "LLM", "Generative AI",
    "GenAI", "NLP", "OpenCV", "AWS", "GCP", "Kubernetes", "Node.js", "Django", "Flask",
    "Pandas", "NumPy", "Claude Code", "LlamaIndex", "Hugging Face", "Ollama", "vLLM",
    "Agentic AI", "ReAct", "REST APIs", "Automation", "Scikit-Learn", "Prompt Engineering",
]

BASE_SEARCH_TERMS = [
    "part-time", "contract", "freelance", "remote", "junior", "entry-level", "0-2 years",
]


def extract_text_from_file(content: bytes, filename: str) -> str:
    """Extract plain text from uploaded PDF or text file."""
    ext = (filename or "").lower().split(".")[-1]
    if ext == "pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content))
            pages_text = []
            for i, page in enumerate(reader.pages):
                extracted = page.extract_text() or ""
                if extracted.strip():
                    pages_text.append(extracted.strip())
            return "\n\n".join(pages_text)
        except Exception as exc:
            logger.exception("PDF extraction failed: %s", exc)
            raise ValueError(f"Failed to read PDF: {exc}") from exc
    else:
        # Text, Markdown, CSV, etc.
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("latin-1", errors="replace")


def parse_resume(db: Session, raw_text: str) -> dict[str, Any]:
    """Parse resume text using LLM if available, otherwise deterministic heuristics."""
    clean_text = raw_text.strip()
    if not clean_text:
        raise ValueError("Resume file is empty or text could not be extracted.")

    ready, _ = llm.provider_ready()
    if ready:
        try:
            return _parse_with_llm(db, clean_text)
        except Exception as exc:
            logger.warning("LLM resume parsing failed (%s), falling back to heuristics", exc)

    return _parse_with_heuristics(clean_text)


def _parse_with_llm(db: Session, text: str) -> dict[str, Any]:
    system = (
        "You analyze an engineering resume to produce structured outreach profile information. "
        "Reply with strict JSON only matching this schema:\n"
        "{\n"
        '  "about_me": "<3-5 paragraph candidate bio covering current role, flagship projects, core skills, and contract/part-time AI engineering goal>",\n'
        '  "skills": ["<skill1>", "<skill2>", ...],\n'
        '  "search_keywords": ["<lowercased keyword/tag for job search collectors>", ...],\n'
        '  "experience_years": <number of years of professional experience, e.g. 1>\n'
        "}\n"
        "Include 10-18 search_keywords (e.g. python, llm, langchain, rag, agents, genai, junior, contract, remote)."
    )
    user = f"RESUME TEXT:\n{text[:8000]}"
    data, _ = llm.complete_json(
        db,
        system=system,
        user=user,
        purpose="enrich",
        model=None,  # default / fast model
        max_tokens=1500,
        temperature=0.1,
    )

    about_me = str(data.get("about_me") or "").strip()
    skills = [str(s).strip() for s in (data.get("skills") or []) if str(s).strip()]
    keywords = [str(k).lower().strip() for k in (data.get("search_keywords") or []) if str(k).strip()]

    # Ensure base constraints are preserved in search keywords
    for base in BASE_SEARCH_TERMS:
        if base not in keywords:
            keywords.append(base)

    return {
        "about_me": about_me or text[:1500],
        "skills": skills or ["Python", "AI", "LLM"],
        "search_keywords": keywords,
        "experience_years": data.get("experience_years", 1),
    }


def _parse_with_heuristics(text: str) -> dict[str, Any]:
    low = text.lower()

    # Match skills from dictionary
    detected_skills = []
    for skill in TECH_DICTIONARY:
        pattern = rf"\b{re.escape(skill.lower())}\b"
        if re.search(pattern, low):
            detected_skills.append(skill)

    if not detected_skills:
        detected_skills = ["Python", "GenAI", "LLM", "REST APIs", "Git"]

    # Generate search keywords
    search_keywords = [s.lower() for s in detected_skills[:10]]
    for term in BASE_SEARCH_TERMS:
        if term not in search_keywords:
            search_keywords.append(term)

    # Clean lines for about_me summary
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    header_lines = lines[:6]
    summary_parts = ["\n".join(header_lines)]

    # Look for projects section
    project_idx = None
    for idx, line in enumerate(lines):
        if re.search(r"\b(projects|experience|flagship)\b", line, re.I):
            project_idx = idx
            break

    if project_idx is not None:
        summary_parts.append("\n".join(lines[project_idx : project_idx + 18]))
    else:
        summary_parts.append("\n".join(lines[6:24]))

    summary_parts.append(
        "\nSkills: "
        + ", ".join(detected_skills)
        + "\n\nGoal: remote part-time or contract AI/GenAI engineering work (0-2 years bracket, "
        "LLM apps, agents, RAG, evals), eager to learn and happy to start with a small paid trial task."
    )

    about_me = "\n\n".join(summary_parts).strip()

    return {
        "about_me": about_me,
        "skills": detected_skills,
        "search_keywords": search_keywords,
        "experience_years": 1,
    }


def sync_collector_search_filters(db: Session, search_keywords: list[str]) -> list[str]:
    """Sync search keywords into all collectors' configurations."""
    clean_keywords = []
    seen = set()
    for kw in search_keywords:
        k = kw.lower().strip()
        if k and k not in seen:
            seen.add(k)
            clean_keywords.append(k)

    # Always ensure 0-2 YOE and remote contract keywords are present
    for mandatory in ("remote", "part-time", "contract", "junior", "0-2 years"):
        if mandatory not in seen:
            clean_keywords.append(mandatory)
            seen.add(mandatory)

    updated_keys = []
    collectors = db.query(Collector).all()
    for col in collectors:
        cfg = dict(col.config or {})
        existing = cfg.get("keywords")
        if isinstance(existing, list):
            # Merge with existing, prioritizing new resume keywords
            merged = list(clean_keywords)
            for ex in existing:
                ex_low = str(ex).lower().strip()
                if ex_low and ex_low not in seen:
                    merged.append(ex_low)
                    seen.add(ex_low)
            cfg["keywords"] = merged[:25]  # Keep reasonable top keyword list
        else:
            cfg["keywords"] = clean_keywords[:20]

        col.config = cfg
        updated_keys.append(col.key)

    db.commit()
    return updated_keys
