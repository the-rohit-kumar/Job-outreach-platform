"""Dashboard numbers: today's progress, funnel, reply rate by source."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Draft, FollowUp, Lead, Message, SendEvent
from . import warmup


def _today() -> str:
    return warmup.day_key()


def dashboard(db: Session) -> dict:
    today = _today()
    now = datetime.now(timezone.utc)
    since_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    collected_today = (
        db.query(func.count(Lead.id)).filter(Lead.created_at >= since_midnight).scalar() or 0
    )
    qualified_today = (
        db.query(func.count(Lead.id))
        .filter(
            Lead.created_at >= since_midnight,
            Lead.status.in_(("qualified", "enriched", "drafted", "replied", "sent")),
        )
        .scalar()
        or 0
    )
    drafted_today = (
        db.query(func.count(Draft.id)).filter(Draft.created_at >= since_midnight).scalar() or 0
    )
    sent_today_email = (
        db.query(func.count(SendEvent.id))
        .filter(
            SendEvent.day_key == today,
            SendEvent.channel == "email",
            SendEvent.status.in_(("sent", "confirmed")),
        )
        .scalar()
        or 0
    )
    sent_today_platform = (
        db.query(func.count(SendEvent.id))
        .filter(
            SendEvent.day_key == today,
            SendEvent.channel == "platform",
            SendEvent.status.in_(("sent", "confirmed")),
        )
        .scalar()
        or 0
    )
    replies_today = (
        db.query(func.count(Message.id))
        .filter(Message.direction == "in", Message.received_at >= since_midnight)
        .scalar()
        or 0
    )

    funnel = _funnel(db)
    return {
        "date": today,
        "counts": {
            "collected": collected_today,
            "qualified": qualified_today,
            "drafted": drafted_today,
            "sent_email": sent_today_email,
            "sent_platform": sent_today_platform,
            "sent": sent_today_email + sent_today_platform,
            "replied": replies_today,
        },
        "targets": _targets(db),
        "funnel": funnel,
        "reply_rate_by_source": reply_rate_by_source(db),
        "followups_due": db.query(func.count(FollowUp.id))
        .filter(FollowUp.status == "due", FollowUp.due_at <= now)
        .scalar()
        or 0,
        "warmup": warmup.email_status(db),
        "platform_warmup": warmup.platform_status(db),
        "review_queue": {
            "pending": db.query(func.count(Draft.id)).filter(Draft.status == "pending").scalar() or 0,
            "needs_manual": db.query(func.count(Draft.id))
            .filter(Draft.status == "needs_manual")
            .scalar()
            or 0,
        },
        "llm": llm_summary(db),
    }


def _targets(db: Session) -> dict:
    from ..models import Setting

    def t(key: str, default: int) -> int:
        row = db.get(Setting, key)
        try:
            return int(row.value) if row and row.value is not None else default
        except (TypeError, ValueError):
            return default

    return {
        "collected": t("daily.target_collected", 300),
        "qualified": t("daily.target_qualified", 100),
        "drafts": t("daily.target_drafts", 50),
        "sent": t("daily.target_sent", 35),
    }


def _funnel(db: Session) -> list[dict]:
    stages = ["new", "qualified", "enriched", "drafted", "sent", "replied"]
    counts = dict(
        db.query(Lead.stage, func.count(Lead.id)).group_by(Lead.stage).all()
    )
    status_counts = dict(db.query(Lead.status, func.count(Lead.id)).group_by(Lead.status).all())
    return [
        {"label": "Collected", "value": sum(status_counts.values())},
        {
            "label": "Qualified",
            "value": status_counts.get("qualified", 0)
            + status_counts.get("enriched", 0)
            + status_counts.get("drafted", 0)
            + status_counts.get("replied", 0),
        },
        {"label": "Drafted", "value": counts.get("drafted", 0) + counts.get("sent", 0)},
        {"label": "Sent", "value": counts.get("sent", 0)},
        {"label": "Replied", "value": counts.get("replied", 0)},
    ]


def reply_rate_by_source(db: Session) -> list[dict]:
    rows = (
        db.query(Lead.source, func.count(Lead.id))
        .filter(Lead.contacted_at.isnot(None))
        .group_by(Lead.source)
        .all()
    )
    out = []
    for source, sent in rows:
        replies = (
            db.query(func.count(Lead.id))
            .filter(Lead.source == source, Lead.replied_at.isnot(None))
            .scalar()
            or 0
        )
        out.append(
            {
                "source": source,
                "sent": sent,
                "replies": replies,
                "reply_rate": round(replies / sent, 4) if sent else 0.0,
            }
        )
    return sorted(out, key=lambda r: (-r["reply_rate"], -r["sent"]))


def llm_summary(db: Session) -> dict:
    from .llm import spend_today

    from ..models import UsageEvent

    today = _today()
    events = db.query(UsageEvent).filter(UsageEvent.day_key == today).all()
    return {
        "calls_today": len(events),
        "spend_today_usd": round(spend_today(db), 4),
        "fallback_calls": sum(1 for e in events if not e.model),
    }
