"""We Work Remotely - public RSS feeds."""
from __future__ import annotations

from datetime import timezone

import feedparser

from .base import BaseCollector, CollectorContext, NormalizedLead, strip_html, keyword_hit


class WWRCollector(BaseCollector):
    key = "wwr"
    name = "We Work Remotely (RSS)"
    kind = "rss"
    default_config = {
        "feeds": [
            "https://weworkremotely.com/categories/remote-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
        ],
        "keywords": ["python", "engineer", "developer", "ai", "machine learning", "backend"],
        "inter_request_pause": 1.0,
        "cache_ttl_seconds": 1800,
    }

    def fetch(self, ctx: CollectorContext) -> list[NormalizedLead]:
        keywords = [k.lower() for k in ctx.config.get("keywords", [])]
        leads: list[NormalizedLead] = []
        seen: set[str] = set()
        for feed_url in ctx.config.get("feeds", []):
            xml = ctx.get_text(feed_url)
            parsed = feedparser.parse(xml)
            for entry in parsed.entries:
                title = strip_html(entry.get("title", ""))
                # WWR titles look like "Job Title - Company - Country"
                parts = [p.strip() for p in title.split(" - ")]
                company = parts[1] if len(parts) > 1 else ""
                headline = parts[0] if parts else title
                summary = strip_html(entry.get("summary", ""))
                haystack = f"{title} {summary}".lower()
                if not keyword_hit(haystack, keywords):
                    continue
                link = entry.get("link", "")
                if not link or link in seen:
                    continue
                seen.add(link)
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                posted_at = None
                if published:
                    from datetime import datetime

                    posted_at = datetime(*published[:6], tzinfo=timezone.utc)
                leads.append(
                    NormalizedLead(
                        source="wwr",
                        title=headline,
                        company=company,
                        url=entry.get("link", ""),
                        description=summary[:4000],
                        location=parts[2] if len(parts) > 2 else "",
                        remote=True,
                        employment_type="full-time",
                        posted_at=posted_at,
                        raw_text=f"{title}\n{summary}",
                    )
                )
        return leads
