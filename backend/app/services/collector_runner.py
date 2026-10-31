"""Run collectors safely: registry sync, robots, rate limits, error isolation."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..collectors import REGISTRY, RobotsChecker, get_collector
from ..config import settings
from ..models import Collector, CollectorRun, Lead, utcnow
from .leads import upsert_lead

logger = logging.getLogger("outreachhub.collectors")


def cache_dir() -> Path:
    return Path(settings.cache_dir)


@dataclass
class RunResult:
    key: str
    status: str  # ok | error | skipped | partial
    found: int = 0
    new: int = 0
    duplicates: int = 0
    suppressed: int = 0
    error: str = ""
    run_id: int | None = None
    duration_ms: int = 0
    leads: list[Lead] = field(default_factory=list)


def sync_registry(db: Session) -> None:
    """Create/update collectors table rows from the code registry."""
    for key, collector in REGISTRY.items():
        row = db.get(Collector, key)
        if row is None:
            db.add(
                Collector(
                    key=key,
                    name=collector.name,
                    kind=collector.kind,
                    enabled=False,
                    config=dict(collector.default_config),
                )
            )
        else:
            row.name = collector.name
            row.kind = collector.kind
            merged = dict(collector.default_config)
            merged.update(row.config or {})
            row.config = merged
    db.commit()


def _merge_config(row: Collector) -> dict[str, Any]:
    collector = get_collector(row.key)
    base = dict(collector.default_config) if collector else {}
    # YAML config (repo) wins over code defaults, DB row wins over both.
    from ..config import sources_config

    base.update(sources_config.get(row.key, {}))
    base.update(row.config or {})
    return base


def run_collector(
    db: Session,
    key: str,
    *,
    force: bool = False,
    transport=None,
) -> RunResult:
    started = utcnow()
    collector = get_collector(key)
    if collector is None:
        return RunResult(key=key, status="error", error=f"Unknown collector '{key}'")

    row = db.get(Collector, key)
    if row is None:
        from .collector_runner import sync_registry

        sync_registry(db)
        row = db.get(Collector, key)
    assert row is not None

    if not row.enabled and not force:
        return RunResult(key=key, status="skipped", error="disabled")

    config = _merge_config(row)
    if not force and row.last_run_at is not None:
        min_interval = int(config.get("min_interval_seconds", 300))
        last = row.last_run_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - last < timedelta(seconds=min_interval):
            return RunResult(
                key=key,
                status="skipped",
                error=f"rate limit: ran {int((datetime.now(timezone.utc) - last).total_seconds())}s ago "
                f"(min interval {min_interval}s)",
            )

    run = CollectorRun(collector_key=key, started_at=started, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)

    ctx = collector.build_context(
        config,
        transport=transport,
        cache_dir=cache_dir(),
        robots=RobotsChecker(cache_dir() / "robots", transport=transport),
    )
    result = RunResult(key=key, status="ok")
    try:
        normalized = collector.fetch(ctx)
        result.found = len(normalized)
        for item in normalized:
            lead, outcome = upsert_lead(db, item, source=item.source)
            if outcome == "created":
                result.new += 1
                result.leads.append(lead)
            elif outcome == "duplicate":
                result.duplicates += 1
            elif outcome == "suppressed":
                result.suppressed += 1
    except PermissionError as exc:
        result.status = "error"
        result.error = str(exc)
    except Exception as exc:  # noqa: BLE001 - one dead source never stops the pipeline
        logger.exception("Collector %s failed", key)
        result.status = "error"
        result.error = f"{type(exc).__name__}: {exc}"
    finally:
        ctx.close()

    finished = utcnow()
    run.finished_at = finished
    run.status = result.status
    run.leads_found = result.found
    run.leads_new = result.new
    run.error = result.error
    row.last_run_at = finished
    row.last_status = result.status
    row.last_error = result.error
    row.last_count = result.found
    db.commit()

    result.run_id = run.id
    result.duration_ms = int((finished - started).total_seconds() * 1000)
    return result


def run_enabled(db: Session, *, force: bool = False, transport=None) -> list[RunResult]:
    sync_registry(db)
    rows = db.query(Collector).filter(Collector.enabled.is_(True)).all()
    results: list[RunResult] = []
    for row in rows:
        results.append(run_collector(db, row.key, force=force, transport=transport))
    return results


def run_scheduled(db: Session) -> dict[str, Any]:
    """Morning job: collect -> dedupe -> score -> enrich -> draft -> self-check."""
    from . import pipeline

    collect_results = run_enabled(db, force=False)
    summary = {
        "collect": [
            {"key": r.key, "status": r.status, "found": r.found, "new": r.new, "error": r.error}
            for r in collect_results
        ],
        "new_leads": sum(r.new for r in collect_results),
    }
    summary.update(pipeline.run(db))
    return summary


def lead_counts(db: Session) -> dict[str, int]:
    rows = db.query(Lead.status, Lead.id).all()
    counts: dict[str, int] = {}
    for status, _ in rows:
        counts[status] = counts.get(status, 0) + 1
    counts["total"] = len(rows)
    return counts
