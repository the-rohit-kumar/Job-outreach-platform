"""Manual importer: paste text, lines or CSV -> the same Lead pipeline."""
from __future__ import annotations

import csv
import io
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..services.leads import upsert_lead

router = APIRouter(prefix="/api/import", tags=["import"], dependencies=[Depends(get_current_user)])

URL_RE = re.compile(r"https?://[^\s,;\"')>]+")


class TextImportIn(BaseModel):
    text: str = Field(min_length=1)
    source: str = "manual"
    default_remote: bool = True


class CsvImportIn(BaseModel):
    csv: str = Field(min_length=1)
    source: str = "manual"


def _clean(value: str | None) -> str:
    return (value or "").strip()


@router.post("/text")
def import_text(body: TextImportIn, db: Session = Depends(get_db)) -> dict:
    """Supports: bare URLs, 'Title | Company | URL', 'Title, Company, URL'."""
    created = duplicates = suppressed = failed = 0
    results: list[dict] = []
    for raw_line in body.text.splitlines():
        line = _clean(raw_line)
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in re.split(r"[|,]\s*", line) if p.strip()]
        url = ""
        for part in parts:
            found = URL_RE.search(part)
            if found:
                url = found.group(0)
                break
        if not url:
            found = URL_RE.search(line)
            url = found.group(0) if found else ""
        title = parts[0] if parts and not parts[0].startswith("http") else ""
        company = parts[1] if len(parts) > 1 and not parts[1].startswith("http") else ""
        if not url and not title:
            failed += 1
            continue
        lead, outcome = upsert_lead(
            db,
            {
                "source": body.source,
                "title": (title or line)[:255],
                "company": company,
                "url": url,
                "description": line[:4000],
                "raw_text": line[:4000],
                "remote": body.default_remote,
                "contact": {"profile_url": url},
            },
        )
        results.append({"line": line[:80], "outcome": outcome, "lead_id": lead.id if lead else None})
        if outcome == "created":
            created += 1
        elif outcome == "duplicate":
            duplicates += 1
        elif outcome == "suppressed":
            suppressed += 1
        else:
            failed += 1
    return {"created": created, "duplicates": duplicates, "suppressed": suppressed, "failed": failed, "results": results[:50]}


@router.post("/csv")
def import_csv(body: CsvImportIn, db: Session = Depends(get_db)) -> dict:
    reader = csv.DictReader(io.StringIO(body.csv.strip()))
    if not reader.fieldnames:
        raise HTTPException(status_code=422, detail="CSV needs a header row")
    created = duplicates = suppressed = 0
    for row in reader:
        normalized = {(_clean(k)).lower(): _clean(v) for k, v in row.items() if k}
        lead, outcome = upsert_lead(
            db,
            {
                "source": normalized.get("source") or body.source,
                "title": normalized.get("title") or normalized.get("role") or "",
                "company": normalized.get("company") or "",
                "url": normalized.get("url") or normalized.get("link") or "",
                "description": normalized.get("description") or normalized.get("notes") or "",
                "raw_text": str(row),
                "location": normalized.get("location") or "",
                "remote": (normalized.get("remote") or "true").lower() in ("true", "1", "yes"),
                "employment_type": normalized.get("type") or normalized.get("employment_type") or "",
                "contact": {
                    "email": normalized.get("email") or "",
                    "name": normalized.get("name") or "",
                    "profile_url": normalized.get("profile_url") or normalized.get("url") or "",
                },
            },
        )
        if outcome == "created":
            created += 1
        elif outcome == "duplicate":
            duplicates += 1
        elif outcome == "suppressed":
            suppressed += 1
    return {"created": created, "duplicates": duplicates, "suppressed": suppressed}
