"""Remotive - public JSON API."""
from __future__ import annotations

from datetime import datetime

from .base import BaseCollector, CollectorContext, NormalizedLead, strip_html, keyword_hit


class RemotiveCollector(BaseCollector):
    key = "remotive"
    name = "Remotive"
    kind = "api"
    default_config = {
        "endpoint": "https://remotive.com/api/remote-jobs",
        "category": "software-dev",
        "keywords": ["python", "ai", "machine learning", "engineer", "backend", "llm"],
        "inter_request_pause": 1.5,
        "cache_ttl_seconds": 1800,
    }

    def fetch(self, ctx: CollectorContext) -> list[NormalizedLead]:
        params = {}
        if ctx.config.get("category"):
            params["category"] = ctx.config["category"]
        if ctx.config.get("search"):
            params["search"] = ctx.config["search"]
        data = ctx.get_json(ctx.config["endpoint"], params=params or None)
        jobs = data.get("jobs") or []
        keywords = [k.lower() for k in ctx.config.get("keywords", [])]
        leads: list[NormalizedLead] = []
        for job in jobs:
            title = strip_html(str(job.get("title") or ""))
            description = strip_html(str(job.get("description") or ""))
            tags = " ".join(job.get("tags") or [])
            if not keyword_hit(f"{title} {description} {tags}", keywords):
                continue
            posted_at = None
            if job.get("publication_date"):
                try:
                    posted_at = datetime.fromisoformat(
                        str(job["publication_date"]).replace("Z", "+00:00")
                    )
                except ValueError:
                    posted_at = None
            leads.append(
                NormalizedLead(
                    source="remotive",
                    title=title,
                    company=strip_html(str(job.get("company_name") or "")),
                    url=str(job.get("url") or ""),
                    description=description[:4000],
                    location=strip_html(str(job.get("candidate_required_location") or "")),
                    remote=True,
                    employment_type=str(job.get("employment_type") or ""),
                    posted_at=posted_at,
                    raw_text=f"{title}\n{description}",
                )
            )
        return leads
