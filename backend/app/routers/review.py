"""Review Queue API - the human-in-the-loop core.

Actions: approve | edit | skip | regenerate | never_contact
Nothing is ever sent without one of these, one draft at a time.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Draft, Lead, OnboardingItem, Profile, utcnow
from ..services import drafting, sending
from ..services.leads import mark_suppressed
from ..services.self_check import check_draft

router = APIRouter(prefix="/api/review", tags=["review"], dependencies=[Depends(get_current_user)])


class ReviewItemOut(BaseModel):
    draft: dict
    lead: dict
    index: int = 0
    queue_size: int = 0
    variants: list[dict] = Field(default_factory=list)


class ActionIn(BaseModel):
    action: str  # approve | edit | skip | regenerate | never_contact
    body: str | None = None
    subject: str | None = None


def _queue_query(db: Session):
    return (
        db.query(Draft)
        .join(Lead, Draft.lead_id == Lead.id)
        .filter(
            Draft.status == "pending",
            Lead.opted_out.is_(False),
            Lead.duplicate_of.is_(None),
        )
        .order_by(Lead.score.desc().nullslast(), Draft.id)
    )


def _lead_payload(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "source": lead.source,
        "title": lead.title,
        "company": lead.company,
        "url": lead.url,
        "location": lead.location,
        "remote": lead.remote,
        "employment_type": lead.employment_type,
        "score": lead.score,
        "score_reason": lead.score_reason,
        "score_model": lead.score_model,
        "channel": lead.channel,
        "hook": lead.hook,
        "contact": lead.contact,
        "enrichment": lead.enrichment,
        "stage": lead.stage,
        "status": lead.status,
        "description": lead.description[:4000],
        "posted_at": lead.posted_at.isoformat() if lead.posted_at else None,
    }


def _draft_payload(draft: Draft) -> dict:
    return {
        "id": draft.id,
        "lead_id": draft.lead_id,
        "variant": draft.variant,
        "channel": draft.channel,
        "subject": draft.subject,
        "body": draft.body,
        "status": draft.status,
        "generation": draft.generation,
        "model": draft.model,
        "checks": draft.checks,
        "fail_reason": draft.fail_reason,
        "words": len(draft.body.split()) if draft.body else 0,
        "chars": len(draft.body or ""),
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
    }


@router.get("/next", response_model=ReviewItemOut)
def next_draft(db: Session = Depends(get_db)) -> ReviewItemOut:
    query = _queue_query(db)
    total = query.count()
    draft = query.first()
    if draft is None:
        return ReviewItemOut(draft={}, lead={}, index=0, queue_size=0)
    lead = draft.lead
    variants = [
        {"id": d.id, "variant": d.variant, "status": d.status}
        for d in db.query(Draft).filter(Draft.lead_id == lead.id).all()
    ]
    return ReviewItemOut(
        draft=_draft_payload(draft),
        lead=_lead_payload(lead),
        index=0,
        queue_size=total,
        variants=variants,
    )


@router.get("/stats")
def review_stats(db: Session = Depends(get_db)) -> dict:
    pending = _queue_query(db).count()
    needs_manual = db.query(func.count(Draft.id)).filter(Draft.status == "needs_manual").scalar() or 0
    reviewed_today = (
        db.query(func.count(Draft.id))
        .filter(
            Draft.reviewed_at.isnot(None),
            Draft.reviewed_at >= datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ),
        )
        .scalar()
        or 0
    )
    return {"pending": pending, "needs_manual": needs_manual, "reviewed_today": reviewed_today}


@router.get("/needs-manual")
def needs_manual(db: Session = Depends(get_db)) -> list[dict]:
    rows = (
        db.query(Draft)
        .filter(Draft.status == "needs_manual")
        .order_by(Draft.id.desc())
        .limit(100)
        .all()
    )
    return [{"draft": _draft_payload(d), "lead": _lead_payload(m)} for m, d in
            ((db.get(Lead, d.lead_id), d) for d in rows) if m is not None]


@router.post("/{draft_id}/action")
def act(draft_id: int, body: ActionIn, db: Session = Depends(get_db)) -> dict:
    draft = db.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    lead = db.get(Lead, draft.lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    action = body.action

    if action == "edit":
        if body.body is None:
            raise HTTPException(status_code=422, detail="body is required for edit")
        draft.body = body.body
        if body.subject is not None:
            draft.subject = body.subject
        draft.updated_at = utcnow()
        profile = db.get(Profile, 1)
        result = check_draft(db, draft, lead, profile)
        draft.checks = {**result.checks, "reasons": result.reasons}
        draft.fail_reason = "" if result.ok else "; ".join(result.reasons)[:512]
        db.commit()
        return {"ok": True, "action": "edit", "checks_ok": result.ok, "reasons": result.reasons}

    if action == "skip":
        draft.status = "skipped"
        draft.reviewed_at = utcnow()
        db.commit()
        return {"ok": True, "action": "skip"}

    if action == "never_contact":
        draft.status = "rejected"
        draft.reviewed_at = utcnow()
        mark_suppressed(db, lead, reason="user marked never contact", kind="person")
        return {"ok": True, "action": "never_contact"}

    if action == "regenerate":
        profile = db.get(Profile, 1)
        if draft.generation >= 3:
            draft.status = "needs_manual"
            draft.fail_reason = "regenerated twice without passing the self-check"
            db.commit()
            return {"ok": True, "action": "regenerate", "status": "needs_manual"}
        fresh = drafting._generate(db, lead, profile, draft.variant)
        draft.generation += 1
        draft.body = fresh.body
        draft.subject = fresh.subject
        draft.model = fresh.model
        draft.updated_at = utcnow()
        result = check_draft(db, draft, lead, profile)
        draft.checks = {**result.checks, "reasons": result.reasons}
        draft.fail_reason = "" if result.ok else "; ".join(result.reasons)[:512]
        if not result.ok and draft.generation >= 2:
            draft.status = "needs_manual"
        db.commit()
        return {
            "ok": True,
            "action": "regenerate",
            "draft": _draft_payload(draft),
            "checks_ok": result.ok,
            "reasons": result.reasons,
        }

    if action == "approve":
        if body.body is not None:
            draft.body = body.body
        if body.subject is not None:
            draft.subject = body.subject
        profile = db.get(Profile, 1)
        result = check_draft(db, draft, lead, profile)
        if not result.ok:
            draft.checks = {**result.checks, "reasons": result.reasons}
            draft.fail_reason = "; ".join(result.reasons)[:512]
            db.commit()
            return {
                "ok": False,
                "action": "approve",
                "blocked": "self_check",
                "reasons": result.reasons,
            }

        if draft.channel == "email":
            if not (lead.contact or {}).get("email"):
                draft.status = "needs_manual"
                draft.fail_reason = "no public email address - use a platform channel"
                db.commit()
                return {"ok": False, "action": "approve", "blocked": "no_email"}
            try:
                event = sending.approve_email_draft(db, draft, lead)
            except sending.SendBlocked as exc:
                return {"ok": False, "action": "approve", "blocked": str(exc)}
            draft.status = "approved"
            draft.reviewed_at = utcnow()
            db.commit()
            _mark_first_review(db)
            return {
                "ok": True,
                "action": "approve",
                "queued": True,
                "send_event_id": event.id,
                "message": "Queued - it sends automatically inside your window and caps.",
            }

        # platform channel: recorded only after you confirm you pressed Send
        draft.status = "approved"
        draft.reviewed_at = utcnow()
        db.commit()
        _mark_first_review(db)
        return {
            "ok": True,
            "action": "approve",
            "queued": False,
            "message": "Approved. Copy or Fill the draft, send it yourself, then confirm sent.",
        }

    raise HTTPException(status_code=422, detail=f"Unknown action '{action}'")


def _mark_first_review(db: Session) -> None:
    item = db.get(OnboardingItem, "first_review")
    if item is not None and not item.done:
        item.done = True
        db.commit()
