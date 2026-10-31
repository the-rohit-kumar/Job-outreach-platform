"""GitHub - public search API for small, active repos building LLM apps."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .base import BaseCollector, CollectorContext, NormalizedLead, strip_html


class GitHubCollector(BaseCollector):
    key = "github"
    name = "GitHub (repos building LLM apps)"
    kind = "api"
    default_config = {
        "queries": [
            "langchain rag",
            "langgraph agent",
            "llm evaluation",
            "mcp server ai",
            "vector database rag",
            "llamaindex agent",
        ],
        "created_within_days": 120,
        "max_stars": 500,
        "sort": "updated",
        "inter_request_pause": 8.0,  # unauthenticated search API allows 10 req/min
        "cache_ttl_seconds": 3600,
    }
    API = "https://api.github.com"

    def fetch(self, ctx: CollectorContext) -> list[NormalizedLead]:
        headers = {"Accept": "application/vnd.github+json"}
        if ctx.config.get("token"):
            headers["Authorization"] = f"Bearer {ctx.config['token']}"
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=int(ctx.config.get("created_within_days", 120))
        )
        max_stars = int(ctx.config.get("max_stars", 500))
        leads: list[NormalizedLead] = []
        seen: set[str] = set()

        for query in ctx.config.get("queries", []):
            resp = ctx.client.get(
                f"{self.API}/search/repositories",
                params={
                    "q": query,
                    "sort": ctx.config.get("sort", "updated"),
                    "order": "desc",
                    "per_page": 30,
                },
                headers=headers,
            )
            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                raise PermissionError("GitHub API rate limit hit (search: 10/min unauthenticated)")
            if resp.status_code in (401, 403):
                raise PermissionError(f"GitHub API refused the request ({resp.status_code})")
            resp.raise_for_status()
            for repo in resp.json().get("items", []):
                full_name = repo.get("full_name") or ""
                if not full_name or full_name in seen:
                    continue
                seen.add(full_name)
                if repo.get("archived") or repo.get("disabled"):
                    continue
                if int(repo.get("stargazers_count") or 0) > max_stars:
                    continue
                created = _parse(repo.get("created_at"))
                if created and created < cutoff:
                    continue
                topics = " ".join(repo.get("topics") or [])
                description = strip_html(str(repo.get("description") or ""))
                haystack = f"{full_name} {description} {topics} {query}".lower()
                if not any(word in haystack for word in ("ai", "llm", "rag", "agent", "langchain", "mcp", "ml")):
                    continue
                owner = repo.get("owner") or {}
                leads.append(
                    NormalizedLead(
                        source="github",
                        title=f"{full_name}: {description[:120] or 'open-source project'}",
                        company=owner.get("login") or full_name.split("/")[0],
                        url=repo.get("html_url") or "",
                        description=f"{description}\n\nTopics: {topics}\nStars: {repo.get('stargazers_count')}",
                        location="",
                        remote=True,
                        employment_type="open-source / contribution",
                        posted_at=created,
                        contact={
                            "name": owner.get("login") or "",
                            "profile_url": owner.get("html_url") or "",
                            "platform": "github",
                        },
                        raw_text=f"{full_name}\n{description}\n{topics}",
                    )
                )
        return leads


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
