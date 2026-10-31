"""Collector tests - recorded fixtures only, no network, ever."""
from __future__ import annotations

import pytest

from app.collectors import get_collector
from app.collectors.base import CollectorContext, NormalizedLead, RobotsChecker, strip_html
from app.services import collector_runner
from app.models import Collector, Lead

from .conftest import fixture_json, fixture_text, make_transport


def ctx_for(key: str, mapping: dict, tmp_path, **overrides):
    collector = get_collector(key)
    config = {**collector.default_config, **overrides}
    return CollectorContext(
        config=config,
        transport=make_transport(mapping),
        cache_dir=tmp_path / "cache",
        robots=RobotsChecker(tmp_path / "cache" / "robots", transport=make_transport({})),
    )


# --- HN ---------------------------------------------------------------------
def test_hn_collects_hiring_comments_and_skips_irrelevant(tmp_path):
    ctx = ctx_for(
        "hn",
        {
            "hn.algolia.com/api/v1/search": (
                200,
                fixture_json("hn_story_search.json"),
            ),
        },
        tmp_path,
    )
    # comments endpoint returns the same fixture path pattern; route by tags param
    import httpx

    original = ctx.client

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "tags=comment" in url:
            return httpx.Response(200, json=fixture_json("hn_comments.json"), request=request)
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json=fixture_json("hn_story_search.json"), request=request)
        return httpx.Response(404, json={}, request=request)

    ctx._client = httpx.Client(transport=httpx.MockTransport(handler))
    leads = get_collector("hn").fetch(ctx)
    titles = " ".join(l.title.lower() + l.description.lower() for l in leads)
    assert any("llm engineer" in (l.title.lower()) for l in leads), titles
    assert not any("senior seo" in l.title.lower() for l in leads)
    pixie = next(l for l in leads if "Pixie" in l.company)
    assert pixie.source == "hn"
    assert pixie.remote is True
    assert pixie.contact["platform"] == "hn"
    assert pixie.url.startswith("https://news.ycombinator.com/item?id=")


# --- RemoteOK ---------------------------------------------------------------
def test_remoteok_filters_and_normalizes(tmp_path):
    ctx = ctx_for("remoteok", {"remoteok.com/api": (200, fixture_text("remoteok.json"))}, tmp_path)
    leads = get_collector("remoteok").fetch(ctx)
    assert len(leads) == 1  # legal notice skipped, java role filtered by keywords
    lead = leads[0]
    assert lead.company == "Acme AI"
    assert lead.remote is True
    assert lead.url.startswith("https://remoteok.com/")
    assert "LLM evaluation" in lead.description


# --- WWR --------------------------------------------------------------------
def test_wwr_parses_rss_and_filters(tmp_path):
    ctx = ctx_for(
        "wwr",
        {"weworkremotely.com": (200, fixture_text("wwr.rss"), "application/rss+xml")},
        tmp_path,
    )
    leads = get_collector("wwr").fetch(ctx)
    assert len(leads) == 1
    lead = leads[0]
    assert lead.company == "Lantern"
    assert "Backend Engineer" in lead.title
    assert lead.remote is True
    assert lead.posted_at is not None


# --- Remotive ---------------------------------------------------------------
def test_remotive_filters(tmp_path):
    ctx = ctx_for("remotive", {"remotive.com/api": (200, fixture_text("remotive.json"))}, tmp_path)
    leads = get_collector("remotive").fetch(ctx)
    assert len(leads) == 1
    assert leads[0].title.startswith("Machine Learning Engineer")
    assert leads[0].company == "Riverstone AI"
    assert leads[0].employment_type == "contract"


# --- GitHub -----------------------------------------------------------------
def test_github_filters_by_stars_and_age(tmp_path):
    ctx = ctx_for("github", {"api.github.com/search": (200, fixture_text("github_search.json"))}, tmp_path)
    leads = get_collector("github").fetch(ctx)
    names = [l.title for l in leads]
    assert any("nova-eval" in n for n in names)
    assert not any("huge-framework" in n for n in names)  # too many stars
    assert not any("legacy-ml" in n for n in names)  # too old
    assert leads[0].contact["platform"] == "github"


# --- framework guarantees ---------------------------------------------------
def test_robots_disallow_blocks_fetch(tmp_path):
    robots = RobotsChecker(tmp_path / "robots", transport=make_transport({
        "example.com/robots.txt": (200, "User-agent: *\nDisallow: /jobs/\n"),
    }))
    assert robots.allowed("https://example.com/about") is True
    assert robots.allowed("https://example.com/jobs/123") is False


def test_robots_fails_open_when_unreachable(tmp_path):
    robots = RobotsChecker(tmp_path / "robots", transport=make_transport({}))
    #404 robots.txt -> everything allowed
    assert robots.allowed("https://nowhere.example/anything") is True


def test_strip_html():
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_collector_errors_are_isolated(db, authed):
    """A dead source records an error without stopping anything else."""
    from app.collectors.base import BaseCollector

    class BoomCollector(BaseCollector):
        key = "boom"
        name = "Boom"
        default_config = {}

        def fetch(self, ctx):
            raise RuntimeError("kaput")

    import app.collectors.registry as registry

    registry.REGISTRY["boom"] = BoomCollector()
    try:
        db.add(Collector(key="boom", name="Boom", enabled=True, config={}))
        db.commit()
        result = collector_runner.run_collector(db, "boom", force=True)
        assert result.status == "error"
        assert "kaput" in result.error
        # pipeline still fine
        assert collector_runner.run_collector(db, "boom", force=True).status == "error"
    finally:
        registry.REGISTRY.pop("boom", None)
        db.query(Collector).filter(Collector.key == "boom").delete()
        from app.models import CollectorRun

        db.query(CollectorRun).filter(CollectorRun.collector_key == "boom").delete()
        db.commit()


def test_run_collector_inserts_leads(db, tmp_path):
    import os
    from app.config import settings

    old = settings.cache_dir
    settings.cache_dir = str(tmp_path / "cache")
    try:
        collector_runner.sync_registry(db)
        result = collector_runner.run_collector(
            db, "remoteok", force=True, transport=make_transport({"remoteok.com/api": (200, fixture_text("remoteok.json"))})
        )
        assert result.status == "ok"
        assert result.found == 1
        assert result.new == 1
        lead = db.query(Lead).filter(Lead.source == "remoteok").first()
        assert lead is not None
        # second run is a duplicate, not a new lead
        result2 = collector_runner.run_collector(
            db, "remoteok", force=True, transport=make_transport({"remoteok.com/api": (200, fixture_text("remoteok.json"))})
        )
        assert result2.new == 0
        assert result2.duplicates == 1
    finally:
        settings.cache_dir = old


def test_disabled_collector_is_skipped(db):
    collector_runner.sync_registry(db)
    result = collector_runner.run_collector(db, "wwr", force=False)
    assert result.status == "skipped"
