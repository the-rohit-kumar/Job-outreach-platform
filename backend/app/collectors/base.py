"""Collector plugin framework.

Every collector:
- returns normalized Lead objects,
- honors robots.txt, terms, rate limits and caching,
- sets a descriptive User-Agent,
- fails gracefully (the pipeline never dies because one source did).

Tests inject an ``httpx.MockTransport`` so no test ever touches the network.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from ..config import settings

USER_AGENT = (
    "OutreachHub/0.1 (local job-search tool; collects public postings only; "
    "+https://github.com/the-rohit-kumar)"
)
DEFAULT_TIMEOUT = 20.0
TAG_RE = re.compile(r"<[^>]+>")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text or "")
    text = TAG_RE.sub(" ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def slugify(value: str) -> str:
    value = (value or "").lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:120]


@dataclass
class NormalizedLead:
    source: str
    title: str
    company: str = ""
    url: str = ""
    description: str = ""
    location: str = ""
    remote: bool = False
    employment_type: str = ""
    posted_at: datetime | None = None
    contact: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "title": self.title,
            "company": self.company,
            "url": self.url,
            "description": self.description,
            "location": self.location,
            "remote": self.remote,
            "employment_type": self.employment_type,
            "posted_at": self.posted_at,
            "contact": self.contact,
            "raw_text": self.raw_text or self.description,
        }


def keyword_hit(text: str, keywords: list[str]) -> bool:
    """Word-aware keyword match: 'engineer' does not match 'engineering'."""
    if not keywords:
        return True
    low = f" {re.sub(r'[^a-z0-9]+', ' ', (text or '').lower())} "
    for keyword in keywords:
        norm = re.sub(r"[^a-z0-9]+", " ", (keyword or "").lower()).strip()
        if norm and f" {norm} " in low:
            return True
    return False


class RobotsChecker:
    """Per-host robots.txt cache. Fails open on network errors (a missing or
    unreachable robots.txt must not break the pipeline) but never fails open
    on an explicit Disallow."""

    def __init__(
        self,
        cache_dir: Path,
        transport: httpx.BaseTransport | None = None,
        ttl: int = 6 * 3600,
    ) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.transport = transport
        self.ttl = ttl
        self._rules: dict[str, tuple[float, list[tuple[str, str]]]] = {}

    def _fetch(self, netloc: str) -> list[tuple[str, str]]:
        cache_file = self.cache_dir / f"robots-{hashlib.sha1(netloc.encode()).hexdigest()[:16]}.json"
        now = time.time()
        if netloc in self._rules and self._rules[netloc][0] > now:
            return self._rules[netloc][1]
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                if data.get("fetched_at", 0) > now - self.ttl:
                    rules = [tuple(r) for r in data.get("rules", [])]
                    self._rules[netloc] = (now, rules)
                    return rules
            except Exception:
                pass
        rules: list[tuple[str, str]] = []
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=10.0,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            ) as client:
                resp = client.get(f"https://{netloc}/robots.txt")
                body = resp.text if resp.status_code == 200 else ""
                # accept any non-HTML body; reject soft-404 HTML error pages
                if body and "<html" not in body[:400].lower():
                    rules = self._parse(body)
        except Exception:
            rules = []  # fail open on network errors
        try:
            cache_file.write_text(
                json.dumps({"fetched_at": now, "rules": [list(r) for r in rules]}),
                encoding="utf-8",
            )
        except Exception:
            pass
        self._rules[netloc] = (now, rules)
        return rules

    @staticmethod
    def _parse(text: str) -> list[tuple[str, str]]:
        rules: list[tuple[str, str]] = []
        applies = True
        for raw in (text or "").splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            field_name, _, value = line.partition(":")
            field_name = field_name.strip().lower()
            value = value.strip()
            if field_name == "user-agent":
                applies = value in ("*",)
            elif applies and field_name in ("disallow", "allow"):
                rules.append((field_name, value))
        return rules

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        rules = self._fetch(parsed.netloc)
        path = parsed.path or "/"
        best: tuple[int, str, str] | None = None
        for action, pattern in rules:
            if not pattern:
                continue
            if path.startswith(pattern):
                candidate = (len(pattern), action, pattern)
                if best is None or candidate[0] > best[0] or (
                    candidate[0] == best[0] and action == "allow"
                ):
                    best = candidate
        if best is None:
            return True
        return best[1] == "allow"


class RateLimiter:
    """Minimum spacing between runs of a collector + small inter-request pause."""

    def __init__(self, min_interval: float = 0.0, inter_request_pause: float = 0.0) -> None:
        self.min_interval = min_interval
        self.inter_request_pause = inter_request_pause
        self._last_request = 0.0

    def wait_for_slot(self) -> None:
        if self.inter_request_pause <= 0:
            return
        delta = time.monotonic() - self._last_request
        if delta < self.inter_request_pause:
            time.sleep(self.inter_request_pause - delta)
        self._last_request = time.monotonic()


@dataclass
class CollectorContext:
    config: dict[str, Any]
    transport: httpx.BaseTransport | None = None
    robots: RobotsChecker | None = None
    cache_dir: Path | None = None
    rate: RateLimiter | None = None
    log: Callable[[str], None] = lambda _msg: None
    _client: httpx.Client | None = field(default=None, repr=False)

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                transport=self.transport,
                timeout=DEFAULT_TIMEOUT,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
                follow_redirects=True,
            )
        return self._client

    def get_json(self, url: str, params: dict | None = None, use_cache: bool = True) -> Any:
        return self._request(url, params=params, use_cache=use_cache).json()

    def get_text(self, url: str, params: dict | None = None, use_cache: bool = True) -> str:
        return self._request(url, params=params, use_cache=use_cache).text

    def _request(self, url: str, params: dict | None = None, use_cache: bool = True) -> httpx.Response:
        if self.robots is not None and not self.robots.allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        if self.rate is not None:
            self.rate.wait_for_slot()
        if use_cache:
            cached = self._read_cache(url, params)
            if cached is not None:
                return cached
        resp = self.client.get(url, params=params)
        if resp.status_code >= 500 or resp.status_code == 429:
            raise httpx.HTTPStatusError(
                f"{resp.status_code} from {url}", request=resp.request, response=resp
            )
        resp.raise_for_status()
        if use_cache:
            self._write_cache(url, params, resp)
        return resp

    # --- tiny file cache (feeds and API pages) -----------------------------
    def _cache_key(self, url: str, params: dict | None) -> Path:
        assert self.cache_dir is not None
        blob = json.dumps({"url": url, "params": params or {}}, sort_keys=True)
        return self.cache_dir / (hashlib.sha1(blob.encode()).hexdigest() + ".json")

    def _read_cache(self, url: str, params: dict | None) -> httpx.Response | None:
        if self.cache_dir is None:
            return None
        path = self._cache_key(url, params)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("expires_at", 0) < time.time():
                return None
            return httpx.Response(
                status_code=200,
                headers=data.get("headers", {}),
                content=data.get("content", "").encode("utf-8"),
                request=httpx.Request("GET", url),
            )
        except Exception:
            return None

    def _write_cache(self, url: str, params: dict | None, resp: httpx.Response) -> None:
        if self.cache_dir is None:
            return
        ttl = int(self.config.get("cache_ttl_seconds", 900))
        try:
            path = self._cache_key(url, params)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "expires_at": time.time() + ttl,
                        "headers": dict(resp.headers),
                        "content": resp.text,
                    }
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


class BaseCollector(ABC):
    """Subclass and implement ``fetch``."""

    key: str = ""
    name: str = ""
    kind: str = "api"  # api | rss | search | manual
    default_config: dict[str, Any] = {}

    @abstractmethod
    def fetch(self, ctx: CollectorContext) -> list[NormalizedLead]:
        """Return normalized leads. Raise on failure; the pipeline records it."""

    def build_context(self, config: dict[str, Any] | None, transport=None, cache_dir=None, robots=None):
        merged = {**self.default_config, **(config or {})}
        pause = float(merged.get("inter_request_pause", 1.0))
        return CollectorContext(
            config=merged,
            transport=transport,
            robots=robots,
            cache_dir=cache_dir,
            rate=RateLimiter(
                min_interval=float(merged.get("min_interval_seconds", 300)),
                inter_request_pause=pause,
            ),
        )
