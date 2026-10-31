"""RemoteOK - public JSON API."""
from __future__ import annotations

from datetime import datetime, timezone

from .base import BaseCollector, CollectorContext, NormalizedLead, strip_html, keyword_hit


class RemoteOKCollector(BaseCollector):
    key = "remoteok"
    name = "RemoteOK"
    kind = "api"
    default_config = {
        "endpoint": "https://remoteok.com/api",
        "keywords": [
            "python", "backend", "machine learning", "ai", "llm", "engineer", "ml",
        ],
        "min_interval_seconds": 600,
        "inter_request_pause": 1.0,
        "cache_ttl_seconds": 1800,
    }

    def fetch(self, ctx: CollectorContext) -> list[NormalizedLead]:
        data = ctx.get_json(ctx.config["endpoint"])
        if not isinstance(data, list):
            raise ValueError("Unexpected RemoteOK payload")
        keywords = [k.lower() for k in ctx.config.get("keywords", [])]
        leads: list[NormalizedLead] = []
        for row in data:
            if not isinstance(row, dict) or "legal" in row:
                continue  # first element is a legal notice
            title = strip_html(str(row.get("position") or ""))
            description = strip_html(str(row.get("description") or ""))
            haystack = f"{title} {description} {' '.join(row.get('tags') or [])}".lower()
            if not keyword_hit(haystack, keywords):
                continue
            job_url = str(row.get("url") or "")
            if job_url.startswith("/"):
                job_url = f"https://remoteok.com{job_url}"
            posted = row.get("date")
            posted_at = None
            if posted:
                try:
                    posted_at = datetime.fromisoformat(str(posted)).replace(tzinfo=timezone.utc)
                except ValueError:
                    posted_at = None
            employment = str(row.get("employment_type") or "")
            if not employment and "intern" in title.lower():
                employment = "internship"
            leads.append(
                NormalizedLead(
                    source="remoteok",
                    title=title,
                    company=strip_html(str(row.get("company") or "")),
                    url=job_url,
                    description=description,
                    location=strip_html(str(row.get("location") or "")),
                    remote=True,
                    employment_type=employment,
                    posted_at=posted_at,
                    raw_text=f"{title}\n{description}",
                )
            )
        return leads
