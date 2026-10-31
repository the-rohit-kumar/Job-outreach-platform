"""Dedupe: exact URL (at collect time), company+title keys, fuzzy match,
and a configurable per-company contact cooldown (default 60 days).
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from difflib import SequenceMatcher
from sqlalchemy.orm import Session

from ..models import Lead, Setting

COOLDOWN_DEFAULT_DAYS = 60
FUZZY_THRESHOLD = 0.85


def _cooldown_days(db: Session) -> int:
    row = db.get(Setting, "dedupe.cooldown_days")
    try:
        return int(row.value) if row and row.value is not None else COOLDOWN_DEFAULT_DAYS
    except (TypeError, ValueError):
        return COOLDOWN_DEFAULT_DAYS


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2}


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def run_dedupe(db: Session) -> dict:
    leads = (
        db.query(Lead)
        .filter(Lead.duplicate_of.is_(None), Lead.status.notin_(("duplicate", "suppressed")))
        .order_by(Lead.id)
        .all()
    )

    by_key: dict[str, Lead] = {}
    marked = 0

    # 1) exact company+title key
    for lead in leads:
        key = lead.dedupe_key
        if not key:
            continue
        first = by_key.get(key)
        if first is None:
            by_key[key] = lead
            continue
        _mark_duplicate(db, lead, first)
        marked += 1

    # 2) fuzzy company+title across remaining leads (recent window only)
    alive = [l for l in leads if l.duplicate_of is None and l.status != "duplicate"]
    window = datetime.now(timezone.utc) - timedelta(days=30)
    buckets: dict[str, list[Lead]] = defaultdict(list)
    for lead in alive:
        if lead.created_at and lead.created_at.replace(tzinfo=timezone.utc) < window:
            continue
        company_norm = re.sub(r"[^a-z0-9]", "", (lead.company or "").lower())
        buckets[company_norm[:3] or "zzz"].append(lead)

    seen_pairs: set[tuple[int, int]] = set()
    for bucket in buckets.values():
        for i, a in enumerate(bucket):
            for b in bucket[i + 1 :]:
                pair = (a.id, b.id)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                title_sim = similar(a.title, b.title)
                company_sim = 1.0 if (a.company and a.company == b.company) else similar(
                    a.company, b.company
                )
                if title_sim >= FUZZY_THRESHOLD and company_sim >= 0.9:
                    _mark_duplicate(db, b, a)
                    marked += 1

    # 3) per-company contact cooldown
    cooled = apply_company_cooldown(db)

    return {"marked_duplicate": marked, "cooldown_hits": cooled}


def _mark_duplicate(db: Session, lead: Lead, original: Lead) -> None:
    lead.duplicate_of = original.id
    lead.status = "duplicate"
    db.commit()


def apply_company_cooldown(db: Session) -> int:
    """One contact per company within the cooldown window."""
    days = _cooldown_days(db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    contacted_domains: set[str] = set()
    contacted_companies: set[str] = set()
    for lead in db.query(Lead).filter(Lead.contacted_at.isnot(None)).all():
        if lead.contacted_at and lead.contacted_at.replace(tzinfo=timezone.utc) >= cutoff:
            if lead.company_domain:
                contacted_domains.add(lead.company_domain)
            contacted_companies.add((lead.company or "").strip().lower())

    cooled = 0
    for lead in (
        db.query(Lead)
        .filter(
            Lead.status.in_(("new", "qualified", "enriched", "drafted")),
            Lead.contacted_at.is_(None),
        )
        .all()
    ):
        domain = (lead.company_domain or "").lower()
        company = (lead.company or "").strip().lower()
        if (domain and domain in contacted_domains) or (company and company in contacted_companies):
            if lead.status != "cooldown":
                lead.status = "cooldown"
                db.commit()
                cooled += 1
    return cooled
