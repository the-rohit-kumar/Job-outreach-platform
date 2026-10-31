"""Scheduled jobs (APScheduler). Everything is idempotent and capped.

- pipeline:       collect -> dedupe -> score -> enrich -> draft -> self-check
- outbox:         send approved emails inside the window, respecting warm-up
- replies:        detect replies, stop follow-ups
- followups:      turn due follow-ups into review drafts (never auto-sent)
"""
from __future__ import annotations

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .db import SessionLocal

logger = logging.getLogger("outreachhub.scheduler")

_scheduler: BackgroundScheduler | None = None


def _job_pipeline() -> None:
    from .services import collector_runner

    db = SessionLocal()
    try:
        summary = collector_runner.run_scheduled(db)
        logger.info(
            "pipeline: %s new leads from %s sources",
            summary.get("new_leads"),
            len(summary.get("collect", [])),
        )
    except Exception:  # noqa: BLE001
        logger.exception("scheduled pipeline failed")
    finally:
        db.close()


def _job_outbox() -> None:
    from .services import gmail, sending

    db = SessionLocal()
    try:
        if not gmail.is_connected(db):
            return
        result = sending.process_outbox(db)
        if result.get("sent"):
            logger.info("outbox: sent %s email(s)", result["sent"])
    except Exception:  # noqa: BLE001
        logger.exception("scheduled outbox failed")
    finally:
        db.close()


def _job_replies() -> None:
    from .services import followups, gmail

    db = SessionLocal()
    try:
        if not gmail.is_connected(db):
            return
        gmail.fetch_replies(db)
        followups.apply_inbound_messages(db)
    except Exception:  # noqa: BLE001
        logger.exception("scheduled reply detection failed")
    finally:
        db.close()


def _job_followups() -> None:
    from .services import followups

    db = SessionLocal()
    try:
        followups.process_followups(db)
    except Exception:  # noqa: BLE001
        logger.exception("scheduled follow-up job failed")
    finally:
        db.close()


def start() -> BackgroundScheduler | None:
    global _scheduler
    if os.environ.get("OUTREACH_SCHEDULER", "1") == "0":
        logger.info("scheduler disabled via OUTREACH_SCHEDULER=0")
        return None
    if _scheduler is not None:
        return _scheduler
    scheduler = BackgroundScheduler(timezone="UTC")
    # Collect in the morning and mid-afternoon; collectors still self rate-limit.
    scheduler.add_job(_job_pipeline, CronTrigger(hour=8, minute=0))
    scheduler.add_job(_job_pipeline, CronTrigger(hour=14, minute=0))
    scheduler.add_job(_job_pipeline, CronTrigger(hour=20, minute=0))
    scheduler.add_job(_job_outbox, IntervalTrigger(minutes=1))
    scheduler.add_job(_job_replies, IntervalTrigger(minutes=10))
    scheduler.add_job(_job_followups, IntervalTrigger(hours=1))
    scheduler.start()
    _scheduler = scheduler
    logger.info("scheduler started")
    return scheduler


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
