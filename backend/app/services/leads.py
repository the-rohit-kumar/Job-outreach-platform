"""Lead persistence: hashing, suppression checks, insert-once semantics."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..collectors import NormalizedLead
from ..models import Lead, Suppression


def sha(value: str) -> str:
    return hashlib.sha1((value or "").strip().lower().encode("utf-8")).hexdigest()


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    url = url.split("#", 1)[0]
    return url.rstrip("/")


def url_hash(url: str) -> str:
    return sha(normalize_url(url))


def dedupe_key(company: str, title: str, url: str = "") -> str:
    company_n = " ".join((company or "").lower().split())
    title_n = " ".join((title or "").lower().split())
    if company_n or title_n:
        return sha(f"{company_n}|{title_n}")
    return url_hash(url)


def domain_of(url: str, company: str = "") -> str:
    host = urlparse(url or "").netloc.lower().removeprefix("www.")
    if host:
        return host
    slug = "".join(ch for ch in (company or "").lower() if ch.isalnum())
    return slug[:255]


def suppression_values_for(lead_data: dict) -> list[tuple[str, str]]:
    """(kind, value) pairs to check against the suppression list."""
    values: list[tuple[str, str]] = []
    contact = lead_data.get("contact") or {}
    if contact.get("email"):
        values.append(("email", contact["email"].lower()))
    if contact.get("name"):
        values.append(("person", str(contact["name"]).lower()))
    if lead_data.get("company"):
        values.append(("company", str(lead_data["company"]).lower().strip()))
    if lead_data.get("url"):
        values.append(("url", normalize_url(lead_data["url"]).lower()))
    domain = domain_of(lead_data.get("url", ""), lead_data.get("company", ""))
    if domain:
        values.append(("domain", domain))
    return values


def is_suppressed(db: Session, lead_data: dict) -> Suppression | None:
    values = suppression_values_for(lead_data)
    if not values:
        return None
    clauses = [
        (Suppression.kind == kind) & (Suppression.value == value) for kind, value in values
    ]
    return db.execute(select(Suppression).where(or_(*clauses))).scalars().first()


def upsert_lead(
    db: Session, data: dict | NormalizedLead, *, source: str | None = None
) -> tuple[Lead | None, str]:
    """Insert a lead unless its URL already exists or it is suppressed.

    Returns (lead|None, outcome) where outcome is created|duplicate|suppressed.
    """
    payload = data.as_dict() if isinstance(data, NormalizedLead) else dict(data)
    if source:
        payload["source"] = source
    payload.setdefault("source", "manual")

    uhash = url_hash(payload.get("url", ""))
    dkey = dedupe_key(
        payload.get("company", ""), payload.get("title", ""), payload.get("url", "")
    )

    if uhash:
        existing = db.query(Lead).filter(Lead.url_hash == uhash).first()
        if existing is not None:
            return existing, "duplicate"

    if is_suppressed(db, payload) is not None:
        return None, "suppressed"

    now = datetime.now(timezone.utc)
    lead = Lead(
        source=str(payload.get("source", "manual")),
        dedupe_key=dkey,
        title=str(payload.get("title", ""))[:255],
        company=str(payload.get("company", ""))[:255],
        company_domain=domain_of(payload.get("url", ""), payload.get("company", "")),
        url=str(payload.get("url", ""))[:1024],
        url_hash=uhash,
        description=str(payload.get("description", "")),
        location=str(payload.get("location", ""))[:255],
        remote=bool(payload.get("remote", False)),
        employment_type=str(payload.get("employment_type", ""))[:64],
        posted_at=payload.get("posted_at"),
        contact=payload.get("contact") or {},
        raw_text=str(payload.get("raw_text") or payload.get("description", "")),
        channel="email" if (payload.get("contact") or {}).get("email") else "platform",
        status="new",
        stage="new",
        created_at=now,
        updated_at=now,
    )

    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead, "created"


def mark_suppressed(db: Session, lead: Lead, reason: str, kind: str = "person") -> None:
    """Opt out a lead permanently (honored by every collector and importer)."""
    contact = lead.contact or {}
    value = ""
    if kind == "email" and contact.get("email"):
        value = str(contact["email"]).lower()
    elif kind == "domain":
        value = lead.company_domain
    elif kind == "url":
        value = normalize_url(lead.url).lower()
    else:
        value = str(contact.get("name") or lead.company).lower()
    if value:
        existing = (
            db.query(Suppression)
            .filter(Suppression.kind == kind, Suppression.value == value)
            .first()
        )
        if existing is None:
            db.add(Suppression(kind=kind, value=value, reason=reason, source="lead"))
    lead.opted_out = True
    lead.status = "suppressed"
    lead.stage = "closed"
    lead.stage_updated_at = datetime.now(timezone.utc)
    db.commit()
