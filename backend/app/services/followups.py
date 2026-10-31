"""Follow-ups (one short one after 7 days, then close) and reply handling."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import Draft, FollowUp, Lead, Message, Profile, utcnow
from . import sending

logger = logging.getLogger("outreachhub.followups")

CLOSE_AFTER_FOLLOWUP_DAYS = 7


def apply_inbound_messages(db: Session) -> dict:
    """Any reply stops follow-ups and moves the lead to Replied."""
    rows = db.query(Message).filter(Message.direction == "in").all()
    updated = 0
    for msg in rows:
        lead_id = msg.lead_id
        if lead_id is None and msg.sender:
            lead_id = _find_lead_by_sender(db, msg.sender)
            msg.lead_id = lead_id
        if lead_id is None:
            continue
        lead = db.get(Lead, lead_id)
        if lead is None:
            continue
        if lead.stage not in ("replied", "call", "trial_task", "won"):
            lead.stage = "replied"
            lead.stage_updated_at = utcnow()
            lead.replied_at = lead.replied_at or msg.received_at
            lead.status = "replied"
            updated += 1
        sending.cancel_followups(db, lead.id)
        if msg.draft_id:
            draft = db.get(Draft, msg.draft_id)
            if draft is not None and draft.status == "sent":
                draft.status = "replied"
        db.commit()
    # memory of the conversation: mark drafts replied when sender matches
    return {"replies_applied": updated, "messages": len(rows)}


def _find_lead_by_sender(db: Session, sender: str) -> int | None:
    sender = sender.lower()
    for lead in db.query(Lead).filter(Lead.contacted_at.isnot(None)).limit(1000).all():
        email = str((lead.contact or {}).get("email", "")).lower()
        name = str((lead.contact or {}).get("name", "")).lower()
        if email and email in sender:
            return lead.id
        if name and name in sender and len(name) > 4:
            return lead.id
    return None


def process_followups(db: Session) -> dict:
    """Turn due follow-ups into review-queue drafts (never auto-send)."""
    profile = db.get(Profile, 1)
    created = 0
    closed = 0

    for followup in sending.due_followups(db):
        lead = db.get(Lead, followup.lead_id)
        if lead is None or lead.opted_out or lead.stage in ("replied", "call", "trial_task", "won"):
            followup.status = "cancelled" if lead is None else followup.status
            db.commit()
            continue
        if lead.replied_at:
            followup.status = "cancelled"
            db.commit()
            continue

        if followup.sent_at is not None:
            # second window passed without a reply -> close the lead
            if (
                lead.stage not in ("closed", "won")
                and datetime.now(timezone.utc) - followup.sent_at
                > timedelta(days=CLOSE_AFTER_FOLLOWUP_DAYS)
            ):
                lead.stage = "closed"
                lead.stage_updated_at = utcnow()
                db.commit()
                closed += 1
            continue

        existing = (
            db.query(Draft)
            .filter(
                Draft.lead_id == lead.id,
                Draft.variant == "followup",
                Draft.status.in_(("pending", "approved")),
            )
            .first()
        )
        if existing is not None:
            continue

        body = _followup_body(lead, profile)
        draft = Draft(
            lead_id=lead.id,
            variant="followup",
            channel=lead.channel,
            subject=f"Re: {draft_subject(lead)}",
            body=body,
            status="pending",
            model="followup-template",
            checks={"auto": True, "reasons": []},
        )
        db.add(draft)
        followup.draft_id = draft.id
        db.commit()
        created += 1

    return {"followup_drafts_created": created, "closed": closed}


def draft_subject(lead: Lead) -> str:
    return lead.title[:80] if lead.title else f"{lead.company} - quick follow-up"


def _followup_body(lead: Lead, profile: Profile | None) -> str:
    name = str((lead.contact or {}).get("name") or "").split()
    who = name[0] if name and len(name[0]) < 40 else "there"
    company = lead.company or "your team"
    opt_out = " If this isn't relevant, just tell me and I'll close the loop."
    return (
        f"Hi {who}, short follow-up on my note about {lead.title} at {company} - "
        "I still have plenty of availability this week and would be glad to start with a small "
        "paid trial task (a few hours of work, fixed scope)." + opt_out
    )
