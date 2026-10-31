"""Approvals, the send outbox, platform confirmations and bounce handling.

Rule #1: nothing is sent without a per-message approval made by a human.
Email approvals are queued here and dispatched by the scheduler inside the
send window, respecting warm-up caps, spacing and auto-pause.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import Draft, FollowUp, Lead, SendEvent, utcnow
from . import gmail, warmup

logger = logging.getLogger("outreachhub.sending")

FOLLOW_UP_DAYS = 7


class SendBlocked(RuntimeError):
    pass


def approve_email_draft(db: Session, draft: Draft, lead: Lead | None = None) -> SendEvent:
    """Queue an approved email. Nothing leaves until process_outbox runs."""
    lead = lead or db.get(Lead, draft.lead_id)
    if lead is None:
        raise SendBlocked("Lead missing for this draft")
    if lead.opted_out or lead.status == "suppressed":
        raise SendBlocked("Lead is suppressed / opted out")

    event = SendEvent(
        draft_id=draft.id,
        lead_id=lead.id,
        channel="email",
        provider="gmail",
        status="queued",
        day_key=warmup.day_key(),
        queued_at=utcnow(),
        recipient=str((lead.contact or {}).get("email", "")),
    )
    db.add(event)
    draft.status = "approved"
    draft.reviewed_at = utcnow()
    db.commit()
    db.refresh(event)
    return event


def process_outbox(db: Session, transport=None) -> dict:
    """Dispatch queued emails when window, caps, spacing and pause allow it."""
    paused, reason = warmup.pause_state(db)
    if paused:
        return {"sent": 0, "paused": True, "reason": reason}
    if not warmup.window_open(db):
        return {"sent": 0, "paused": False, "reason": "outside send window"}

    queued = (
        db.query(SendEvent)
        .filter(SendEvent.status == "queued", SendEvent.channel == "email")
        .order_by(SendEvent.queued_at)
        .all()
    )
    sent = 0
    errors = 0
    for event in queued:
        if warmup.sent_today(db, "email") >= warmup.email_daily_cap(db):
            break
        last = warmup.last_email_sent_at(db)
        if last is not None:
            gap = (datetime.now(timezone.utc) - last).total_seconds() / 60
            if gap < warmup.spacing_minutes(db):
                break
        draft = db.get(Draft, event.draft_id) if event.draft_id else None
        if draft is None:
            event.status = "failed"
            event.error = "draft missing"
            db.commit()
            continue
        recipient = event.recipient or str((db.get(Lead, event.lead_id).contact or {}).get("email", ""))
        if not recipient:
            event.status = "failed"
            event.error = "no public email address"
            db.commit()
            draft.status = "needs_manual"
            errors += 1
            continue
        try:
            result = gmail.send_email(db, recipient, draft.subject, draft.body, transport=transport)
        except gmail.GmailNotConnected as exc:
            return {"sent": sent, "paused": True, "reason": str(exc)}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Send failed for event %s", event.id)
            event.status = "failed"
            event.error = str(exc)[:500]
            event.sent_at = utcnow()
            db.commit()
            errors += 1
            _mark_bounce(db, event, str(exc))
            continue

        event.status = "sent"
        event.sent_at = utcnow()
        event.day_key = warmup.day_key()
        event.provider_message_id = result.get("id", "")
        event.thread_id = result.get("thread_id", "")
        draft.status = "sent"
        draft.reviewed_at = draft.reviewed_at or utcnow()
        if lead := db.get(Lead, event.lead_id):
            lead.contacted_at = utcnow()
            lead.stage = "sent"
            lead.stage_updated_at = utcnow()
            _schedule_followup(db, lead, draft)
        db.commit()
        sent += 1
    return {"sent": sent, "errors": errors, "paused": False}


def _schedule_followup(db: Session, lead: Lead, draft: Draft) -> None:
    existing = (
        db.query(FollowUp)
        .filter(FollowUp.lead_id == lead.id, FollowUp.status.in_(("due", "sent")))
        .first()
    )
    if existing is not None:
        return
    db.add(
        FollowUp(
            lead_id=lead.id,
            draft_id=draft.id,
            due_at=datetime.now(timezone.utc) + timedelta(days=FOLLOW_UP_DAYS),
            status="due",
        )
    )


def confirm_platform_send(
    db: Session, *, draft_id: int | None = None, lead_id: int | None = None, platform: str = ""
) -> dict:
    """The human pressed Send in the real site; we only record it."""
    draft = db.get(Draft, draft_id) if draft_id else None
    lead = db.get(Lead, lead_id) if lead_id else (db.get(Lead, draft.lead_id) if draft else None)
    if lead is None:
        raise SendBlocked("Lead not found")

    event = SendEvent(
        draft_id=draft.id if draft else None,
        lead_id=lead.id,
        channel="platform",
        provider="manual",
        status="confirmed",
        day_key=warmup.day_key(),
        queued_at=utcnow(),
        sent_at=utcnow(),
        confirmed_at=utcnow(),
        note=platform or "other",
        recipient=str((lead.contact or {}).get("profile_url", "")),
    )
    db.add(event)
    if draft is not None:
        draft.status = "sent"
        draft.reviewed_at = draft.reviewed_at or utcnow()
    lead.contacted_at = utcnow()
    lead.stage = "sent"
    lead.stage_updated_at = utcnow()
    if draft is not None:
        _schedule_followup(db, lead, draft)
    db.commit()
    return {"ok": True, "lead_id": lead.id, "platform": platform}


def mark_bounced(db: Session, event_id: int, note: str = "") -> None:
    event = db.get(SendEvent, event_id)
    if event is None:
        return
    event.bounce = True
    event.error = note or event.error
    db.commit()
    _mark_bounce(db, event, note)


def _mark_bounce(db: Session, event: SendEvent, error: str) -> None:
    """Hard failures with a bad-address signature suppress the contact."""
    lowered = error.lower()
    if not any(
        key in lowered
        for key in ("550", "5.1.1", "552", "recipient rejected", "does not exist", "invalid recipient")
    ):
        return
    from .leads import mark_suppressed

    lead = db.get(Lead, event.lead_id) if event.lead_id else None
    if lead is not None:
        mark_suppressed(db, lead, reason=f"bounce: {error[:120]}", kind="email")


def cancel_followups(db: Session, lead_id: int) -> int:
    rows = (
        db.query(FollowUp)
        .filter(FollowUp.lead_id == lead_id, FollowUp.status == "due")
        .all()
    )
    for row in rows:
        row.status = "cancelled"
    db.commit()
    return len(rows)


def due_followups(db: Session) -> list[FollowUp]:
    return (
        db.query(FollowUp)
        .filter(FollowUp.status == "due", FollowUp.due_at <= datetime.now(timezone.utc))
        .order_by(FollowUp.due_at)
        .limit(50)
        .all()
    )
