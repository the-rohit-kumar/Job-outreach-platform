"""Enrichment: what the company builds, stack signals, team-size signals,
one specific hook, and a publicly listed contact only.

No contact guessing, nothing behind logins, robots.txt honored for page fetches.
If no public email exists the lead is routed to the platform channel.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx

from ..collectors.base import USER_AGENT, RobotsChecker, strip_html
from ..config import settings
from ..models import Lead, Profile
from ..services.leads import domain_of

logger = logging.getLogger("outreachhub.enrich")

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
MAILTO_RE = re.compile(r'href=["\']mailto:([^"\']+)["\']', re.I)
TEAM_RE = re.compile(r"(?:team of|team of about|we are)\s+(\d{1,3})\s+(?:people|engineers|members)", re.I)
STACK_SIGNALS = [
    "python", "typescript", "react", "node", "fastapi", "django", "flask", "postgres",
    "kubernetes", "aws", "gcp", "pytorch", "tensorflow", "langchain", "langgraph",
    "pinecone", "weaviate", "qdrant", "chroma", "faiss", "openai", "anthropic", "llm",
]

HOOK_MAX = 300


@dataclass
class Enrichment:
    summary: str = ""
    stack: list[str] = field(default_factory=list)
    team_size_hint: str = ""
    public_email: str = ""
    contact_source_url: str = ""
    hook: str = ""
    channel: str = "platform"
    fetched: bool = False
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "summary": self.summary,
            "stack": self.stack,
            "team_size_hint": self.team_size_hint,
            "public_email": self.public_email,
            "contact_source_url": self.contact_source_url,
            "hook": self.hook,
            "channel": self.channel,
            "fetched": self.fetched,
            "error": self.error,
        }


def enrich_lead(
    db,
    lead: Lead,
    *,
    transport=None,
    timeout: float = 15.0,
) -> Enrichment:
    result = Enrichment()
    text_sources = [lead.raw_text or lead.description or "", lead.title or ""]

    target = _enrichment_url(lead)
    html = ""
    if target:
        html = _fetch_html(target, transport=transport, timeout=timeout)
        if html:
            result.fetched = True
            page_text = strip_html(html)
            text_sources.append(page_text[:20000])
            result.public_email = _find_public_email(html, target)
            result.contact_source_url = target if result.public_email else ""
            result.team_size_hint = _team_hint(page_text)
            result.summary = _summary(page_text)
            result.stack = _stack(page_text)
        else:
            result.error = "page fetch failed or disallowed by robots.txt"

    combined = " ".join(text_sources)
    result.hook = _hook(combined, lead)

    # Check for direct email in the post text / description
    if not result.public_email:
        raw_text_combined = f"{lead.raw_text or ''} {lead.description or ''}"
        raw_emails = _find_public_emails_in_text(raw_text_combined)
        if raw_emails:
            result.public_email = raw_emails[0]
            result.contact_source_url = lead.url or "posting"

    result.channel = "email" if result.public_email else "platform"

    contact = dict(lead.contact or {})
    if result.public_email:
        contact.setdefault("email", result.public_email)
        if result.contact_source_url:
            contact["email_source_url"] = result.contact_source_url

    # Detect founder / team lead name from text if name is missing or generic
    current_name = str(contact.get("name") or "").strip()
    if not current_name or current_name.lower() in ("there", "team") or "_" in current_name:
        founder_name = _extract_founder_name(f"{lead.raw_text or ''} {lead.description or ''}")
        if founder_name:
            contact["name"] = founder_name
            contact["role"] = "Founder"

    lead.contact = contact
    lead.enrichment = result.as_dict()
    lead.hook = result.hook
    lead.channel = result.channel
    if lead.status in ("qualified", "new"):
        lead.status = "enriched"
    db.commit()
    return result



def _enrichment_url(lead: Lead) -> str:
    """Where to fetch context from: the posting itself, else the company site."""
    url = lead.url or ""
    host = urlparse(url).netloc.lower()
    blocked_hosts = ("news.ycombinator.com", "twitter.com", "x.com", "linkedin.com", "wellfound.com")
    if url and not any(host.endswith(b) for b in blocked_hosts):
        return url
    domain = lead.company_domain or domain_of(url, lead.company)
    if domain and "." in domain and not any(domain.endswith(b) for b in blocked_hosts):
        return f"https://{domain}"
    return ""


def _fetch_html(url: str, *, transport=None, timeout: float) -> str:
    try:
        from .collector_runner import cache_dir

        robots = RobotsChecker(cache_dir() / "robots", transport=transport)
        if not robots.allowed(url):
            return ""
        resp = httpx.Client(
            transport=transport,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ).get(url)
        if resp.status_code != 200:
            return ""
        ctype = resp.headers.get("content-type", "")
        if "html" not in ctype and "text" not in ctype:
            return ""
        return resp.text[:400_000]
    except Exception as exc:  # graceful: enrichment never kills the pipeline
        logger.debug("enrich fetch failed for %s: %s", url, exc)
        return ""


def _find_public_email(html: str, base_url: str) -> str:
    """Only emails literally printed on a public page. No guessing."""
    candidates: list[str] = []
    for match in MAILTO_RE.findall(html or ""):
        candidates.append(match.split("?")[0])
    for match in EMAIL_RE.findall(strip_html(html or "")[:20000]):
        candidates.append(match)
    blocked = ("example.com", "sentry.io", "wixpress.com", "schema.org", "cloudflare", "@2x", ".png", ".jpg")
    for email in candidates:
        email = email.strip().lower()
        if any(b in email for b in blocked):
            continue
        if email.endswith((".png", ".jpg", ".gif", ".webp")):
            continue
        return email
    return ""


def _find_public_emails_in_text(text: str) -> list[str]:
    candidates: list[str] = EMAIL_RE.findall(text or "")
    blocked = ("example.com", "sentry.io", "wixpress.com", "schema.org", "cloudflare", "@2x", ".png", ".jpg")
    cleaned: list[str] = []
    for email in candidates:
        email = email.strip().lower()
        if any(b in email for b in blocked) or email.endswith((".png", ".jpg", ".gif", ".webp")):
            continue
        if email not in cleaned:
            cleaned.append(email)
    return cleaned


def _extract_founder_name(text: str) -> str:
    patterns = [
        re.compile(r"(?:I'm|I am|My name is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*,?\s*(?:the\s+)?(?:founder|co-founder|ceo|cto)", re.I),
        re.compile(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*\((?:founder|co-founder|ceo|cto)\)", re.I),
        re.compile(r"(?:reach|contact|email|ping)\s+([A-Z][a-z]+)\s*(?:at|on|via)\s+[a-zA-Z0-9._%+-]+@", re.I),
    ]
    for pat in patterns:
        m = pat.search(text or "")
        if m:
            name = m.group(1).strip()
            if 2 <= len(name) <= 40:
                return name
    return ""



def _team_hint(text: str) -> str:
    match = TEAM_RE.search(text or "")
    return f"team of {match.group(1)}" if match else ""


def _summary(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if 60 <= len(paragraph) <= 400:
            return paragraph[:400]
    return text[:300]


def _stack(text: str) -> list[str]:
    low = (text or "").lower()
    return sorted({s for s in STACK_SIGNALS if s in low})


def _hook(text: str, lead: Lead) -> str:
    """One specific, quotable fact about the product/posting to reference."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    wanted = re.compile(r"\b(we (build|make|are|help|created)|our (product|platform|tool|agent|app)|"
                        r"llm|ai|rag|agent|open[- ]source|launch)", re.I)
    for sentence in sentences[:40]:
        if 40 <= len(sentence) <= HOOK_MAX and wanted.search(sentence):
            return sentence.strip()[:HOOK_MAX]
    # fall back to a strong line from the posting itself
    for sentence in sentences[:40]:
        if 40 <= len(sentence) <= HOOK_MAX:
            return sentence.strip()[:HOOK_MAX]
    return (lead.title or "")[:HOOK_MAX]


def enrich_new(db, transport=None) -> dict:
    from ..models import Profile  # noqa: F401

    pending = (
        db.query(Lead)
        .filter(Lead.status == "qualified", Lead.duplicate_of.is_(None))
        .limit(200)
        .all()
    )
    done = 0
    for lead in pending:
        try:
            enrich_lead(db, lead, transport=transport)
            done += 1
        except Exception:  # noqa: BLE001
            logger.exception("Enrichment failed for lead %s", lead.id)
    return {"candidates": len(pending), "enriched": done}
