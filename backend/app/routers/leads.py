"""Leads API: filterable table, lead drawer, bulk actions, manual import."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Draft, Lead, Message, utcnow
from ..services import dedupe as dedupe_service
from ..services.leads import mark_suppressed, upsert_lead

router = APIRouter(prefix="/api/leads", tags=["leads"], dependencies=[Depends(get_current_user)])


class LeadOut(BaseModel):
    id: int
    source: str
    title: str
    company: str
    company_domain: str
    url: str
    location: str
    remote: bool
    employment_type: str
    posted_at: datetime | None
    status: str
    stage: str
    score: int | None
    score_reason: str
    channel: str
    hook: str
    contact: dict
    duplicate_of: int | None
    opted_out: bool
    created_at: datetime
    updated_at: datetime


class LeadDetailOut(LeadOut):
    description: str
    raw_text: str
    enrichment: dict
    stage_notes: str
    contacted_at: datetime | None
    replied_at: datetime | None


class PageOut(BaseModel):
    items: list[LeadOut]
    total: int
    page: int
    page_size: int
    facets: dict = {}


class BulkAction(BaseModel):
    ids: list[int] = Field(default_factory=list)
    action: str  # never_contact | suppress | mark_duplicate | rescore | draft | delete


class ManualLeadIn(BaseModel):
    title: str = ""
    company: str = ""
    url: str = ""
    description: str = ""
    location: str = ""
    remote: bool = True
    employment_type: str = ""
    source: str = "manual"
    contact: dict = Field(default_factory=dict)


class LeadPatch(BaseModel):
    stage: str | None = None
    stage_notes: str | None = None
    status: str | None = None
    score: int | None = None


SORTABLE = {
    "score": Lead.score,
    "created_at": Lead.created_at,
    "posted_at": Lead.posted_at,
    "company": Lead.company,
}


@router.get("", response_model=PageOut)
def list_leads(
    q: str | None = None,
    source: str | None = None,
    status: str | None = None,
    stage: str | None = None,
    channel: str | None = None,
    min_score: int | None = None,
    remote: bool | None = None,
    employment_type: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> PageOut:
    query = db.query(Lead).filter(Lead.duplicate_of.is_(None))
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Lead.title.ilike(like),
                Lead.company.ilike(like),
                Lead.description.ilike(like),
                Lead.hook.ilike(like),
            )
        )
    if source:
        query = query.filter(Lead.source == source)
    if status:
        query = query.filter(Lead.status == status)
    if stage:
        query = query.filter(Lead.stage == stage)
    if channel:
        query = query.filter(Lead.channel == channel)
    if min_score is not None:
        query = query.filter(Lead.score >= min_score)
    if remote is not None:
        query = query.filter(Lead.remote.is_(remote))
    if employment_type:
        query = query.filter(Lead.employment_type == employment_type)

    total = query.count()
    column = SORTABLE.get(sort, Lead.created_at)
    query = query.order_by(desc(column) if order == "desc" else column)
    rows = query.offset((page - 1) * page_size).limit(page_size).all()

    facets = {
        "sources": [r[0] for r in db.query(Lead.source).distinct().order_by(Lead.source)],
        "statuses": [r[0] for r in db.query(Lead.status).distinct().order_by(Lead.status)],
        "stages": [r[0] for r in db.query(Lead.stage).distinct().order_by(Lead.stage)],
        "channels": [r[0] for r in db.query(Lead.channel).distinct().order_by(Lead.channel)],
    }
    return PageOut(
        items=[LeadOut.model_validate(r, from_attributes=True) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        facets=facets,
    )


@router.get("/{lead_id}", response_model=LeadDetailOut)
def lead_detail(lead_id: int, db: Session = Depends(get_db)) -> LeadDetailOut:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return LeadDetailOut.model_validate(lead, from_attributes=True)


@router.get("/{lead_id}/history")
def lead_history(lead_id: int, db: Session = Depends(get_db)) -> dict:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    drafts = db.query(Draft).filter(Draft.lead_id == lead_id).order_by(Draft.id).all()
    messages = db.query(Message).filter(Message.lead_id == lead_id).order_by(Message.id).all()
    from ..models import SendEvent

    sends = db.query(SendEvent).filter(SendEvent.lead_id == lead_id).order_by(SendEvent.id).all()
    return {
        "drafts": [
            {
                "id": d.id,
                "variant": d.variant,
                "channel": d.channel,
                "subject": d.subject,
                "body": d.body,
                "status": d.status,
                "model": d.model,
                "checks": d.checks,
                "fail_reason": d.fail_reason,
                "created_at": d.created_at,
                "reviewed_at": d.reviewed_at,
            }
            for d in drafts
        ],
        "messages": [
            {
                "id": m.id,
                "direction": m.direction,
                "channel": m.channel,
                "body": m.body[:2000],
                "sender": m.sender,
                "received_at": m.received_at,
            }
            for m in messages
        ],
        "sends": [
            {
                "id": s.id,
                "channel": s.channel,
                "status": s.status,
                "sent_at": s.sent_at,
                "error": s.error,
                "note": s.note,
            }
            for s in sends
        ],
    }


@router.patch("/{lead_id}", response_model=LeadDetailOut)
def patch_lead(lead_id: int, body: LeadPatch, db: Session = Depends(get_db)) -> LeadDetailOut:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    if body.stage is not None:
        lead.stage = body.stage
        lead.stage_updated_at = utcnow()
    if body.stage_notes is not None:
        lead.stage_notes = body.stage_notes
    if body.status is not None:
        lead.status = body.status
    if body.score is not None:
        lead.score = body.score
    lead.updated_at = utcnow()
    db.commit()
    db.refresh(lead)
    return LeadDetailOut.model_validate(lead, from_attributes=True)


@router.post("/bulk")
def bulk(body: BulkAction, db: Session = Depends(get_db)) -> dict:
    leads = db.query(Lead).filter(Lead.id.in_(body.ids)).all()
    if not leads:
        raise HTTPException(status_code=400, detail="No leads selected")
    changed = 0
    for lead in leads:
        if body.action == "never_contact":
            mark_suppressed(db, lead, reason="bulk never-contact", kind="person")
            changed += 1
        elif body.action == "suppress":
            mark_suppressed(db, lead, reason="bulk suppress", kind="domain")
            changed += 1
        elif body.action == "mark_duplicate" and lead.duplicate_of is None:
            lead.status = "duplicate"
            changed += 1
        elif body.action == "rescore":
            lead.status = "new"
            lead.score = None
            changed += 1
        elif body.action == "draft":
            if lead.status in ("qualified", "enriched"):
                lead.status = "enriched" if lead.status == "enriched" else lead.status
                changed += 1
    db.commit()
    if body.action == "rescore":
        from ..services import scoring

        scoring.score_new_leads(db)
    if body.action == "draft":
        from ..services import pipeline

        pipeline.run(db, stages=("draft", "self_check"))
    return {"changed": changed, "action": body.action}


@router.post("/dedupe")
def run_dedupe(db: Session = Depends(get_db)) -> dict:
    return dedupe_service.run_dedupe(db)


@router.post("", response_model=LeadDetailOut)
def manual_create(body: ManualLeadIn, db: Session = Depends(get_db)) -> LeadDetailOut:
    lead, outcome = upsert_lead(
        db,
        {
            "source": body.source,
            "title": body.title,
            "company": body.company,
            "url": body.url,
            "description": body.description,
            "raw_text": body.description,
            "location": body.location,
            "remote": body.remote,
            "employment_type": body.employment_type,
            "contact": body.contact,
        },
    )
    if outcome == "suppressed":
        raise HTTPException(status_code=409, detail="Contact is on the suppression list")
    if lead is None:
        raise HTTPException(status_code=400, detail="Could not create lead")
    return LeadDetailOut.model_validate(lead, from_attributes=True)
