"""Hacker News collectors via the official Algolia API (no scraping)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


from .base import BaseCollector, CollectorContext, NormalizedLead, keyword_hit, strip_html


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


class HNThreadsCollector(BaseCollector):
    key = "hn"
    name = "Hacker News (Who is hiring / Freelancer / Show HN)"
    kind = "api"
    default_config = {
        "threads": [
            {"query": "who is hiring", "mode": "comments"},
            {"query": "freelancer seeking freelancer", "mode": "comments"},
            {"query": "show hn", "mode": "stories"},
            {"query": "launch hn", "mode": "stories"},
        ],
        "keywords": [
            "llm", "langchain", "langgraph", "rag", "agent", "genai", "ai engineer",
            "python", "part-time", "contract", "freelance", "remote",
        ],
        "max_comments_per_thread": 150,
        "inter_request_pause": 0.6,
        "cache_ttl_seconds": 900,
    }

    API = "https://hn.algolia.com/api/v1"

    def fetch(self, ctx: CollectorContext) -> list[NormalizedLead]:
        keywords: list[str] = list(ctx.config.get("keywords", []))
        leads: list[NormalizedLead] = []
        for thread in ctx.config.get("threads", []):
            query = str(thread.get("query", "")).lower()
            mode = thread.get("mode", "comments")
            story = self._latest_story(ctx, query)
            if not story:
                continue
            if mode == "stories":
                lead = self._lead_from_story(story, keywords)
                if lead:
                    leads.append(lead)
                continue
            leads.extend(self._leads_from_comments(ctx, story, keywords))
        return leads

    def _latest_story(self, ctx: CollectorContext, query: str) -> dict[str, Any] | None:
        data = ctx.get_json(
            f"{self.API}/search",
            params={"query": query, "tags": "story", "hitsPerPage": 8},
        )
        hits = data.get("hits") or []
        for hit in hits:
            title = (hit.get("title") or "").lower()
            if query.split()[0] in title:
                return hit
        return hits[0] if hits else None

    def _lead_from_story(self, story: dict, keywords: list[str]) -> NormalizedLead | None:
        title = strip_html(story.get("title") or "")
        text = strip_html(story.get("story_text") or story.get("url") or "")
        if not keyword_hit(f"{title} {text}", keywords):
            return None
        hn_id = story.get("objectID")
        return NormalizedLead(
            source="hn",
            title=title,
            company=strip_html(story.get("author") or ""),
            url=f"https://news.ycombinator.com/item?id={hn_id}",
            description=text[:4000],
            remote="remote" in text.lower() or "remote" in title.lower(),
            posted_at=_parse_dt(story.get("created_at")),
            contact={
                "name": story.get("author") or "",
                "profile_url": f"https://news.ycombinator.com/user?id={story.get('author')}",
                "platform": "hn",
            },
            raw_text=f"{title}\n{text}",
        )

    def _leads_from_comments(
        self, ctx: CollectorContext, story: dict, keywords: list[str]
    ) -> list[NormalizedLead]:
        story_id = story.get("objectID")
        per_page = min(int(ctx.config.get("max_comments_per_thread", 150)), 100)
        leads: list[NormalizedLead] = []
        for page in range(0, 3):
            data = ctx.get_json(
                f"{self.API}/search",
                params={
                    "tags": f"comment,story_{story_id}",
                    "hitsPerPage": per_page,
                    "page": page,
                },
            )
            hits = data.get("hits") or []
            if not hits:
                break
            for hit in hits:
                lead = self._lead_from_comment(hit, story, keywords)
                if lead:
                    leads.append(lead)
            if page + 1 >= int(data.get("nbPages") or 1):
                break
        return leads

    def _lead_from_comment(
        self, comment: dict, story: dict, keywords: list[str]
    ) -> NormalizedLead | None:
        text = strip_html(comment.get("comment_text") or "")
        if len(text) < 60 or not keyword_hit(text, keywords):
            return None
        parts = [p.strip() for p in text.split("|")]
        company = parts[0][:120] if parts else ""
        title = parts[1][:200] if len(parts) > 1 else (story.get("title") or "Hiring post")[:200]
        location = parts[2][:120] if len(parts) > 2 else ""
        if not company or len(company) > 120:
            company = (story.get("title") or "").split(" - ")[0][:120]
        hn_id = comment.get("objectID")
        contact_dict = {

            "name": comment.get("author") or "",
            "profile_url": f"https://news.ycombinator.com/user?id={comment.get('author')}",
            "platform": "hn",
        }
        emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
        blocked = ("example.com", "sentry.io", "wixpress.com", "schema.org", "cloudflare", "@2x", ".png", ".jpg")
        valid_emails = [
            e.strip().lower()
            for e in emails
            if not any(b in e.lower() for b in blocked) and not e.lower().endswith((".png", ".jpg", ".webp"))
        ]
        if valid_emails:
            contact_dict["email"] = valid_emails[0]

        return NormalizedLead(
            source="hn",
            title=title,
            company=company,
            url=f"https://news.ycombinator.com/item?id={hn_id}",
            description=text[:4000],
            location=location,
            remote="remote" in text.lower() or "anywhere" in text.lower(),
            employment_type="contract" if "freelance" in text.lower() else "",
            posted_at=_parse_dt(comment.get("created_at")),
            contact=contact_dict,
            raw_text=text,
        )

