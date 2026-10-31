"""Tracker kanban API."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Lead, utcnow

router = APIRouter(prefix="/api/tracker", tags=["tracker"], dependencies=[Depends(get_current_user)])

COLUMNS = ["drafted", "sent", "replied", "call", "trial_task", "won", "closed"]


class CardOut(BaseModel):
    id: int
    company: str
    title: str
    source: str
    channel: str
    stage: str
    score: int | None
    notes: str
    stage_updated_at: datetime | None
    contacted_at: datetime | None
    replied_at: datetime | None
    url: str


class TrackerPatch(BaseModel):
    stage: str | None = None
    notes: str | None = None


@router.get("")
def board(db: Session = Depends(get_db)) -> dict:
    rows = (
        db.query(Lead)
        .filter(Lead.stage.in_(COLUMNS))
        .order_by(Lead.stage_updated_at.desc().nullslast(), Lead.id.desc())
        .limit(500)
        .all()
    )
    columns = {c: [] for c in COLUMNS}
    for lead in rows:
        card = CardOut(
            id=lead.id,
            company=lead.company,
            title=lead.title,
            source=lead.source,
            channel=lead.channel,
            stage=lead.stage,
            score=lead.score,
            notes=lead.stage_notes or "",
            stage_updated_at=lead.stage_updated_at,
            contacted_at=lead.contacted_at,
            replied_at=lead.replied_at,
            url=lead.url,
        )
        columns[lead.stage].append(card)
    return {"columns": [{"key": c, "cards": columns[c]} for c in COLUMNS]}


@router.post("/{lead_id}")
def update(lead_id: int, body: TrackerPatch, db: Session = Depends(get_db)) -> CardOut:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    if body.stage is not None:
        if body.stage not in COLUMNS:
            raise HTTPException(status_code=422, detail=f"stage must be one of {COLUMNS}")
        lead.stage = body.stage
        lead.stage_updated_at = utcnow()
    if body.notes is not None:
        lead.stage_notes = body.notes
    lead.updated_at = utcnow()
    db.commit()
    db.refresh(lead)
    return CardOut(
        id=lead.id,
        company=lead.company,
        title=lead.title,
        source=lead.source,
        channel=lead.channel,
        stage=lead.stage,
        score=lead.score,
        notes=lead.stage_notes or "",
        stage_updated_at=lead.stage_updated_at,
        contacted_at=lead.contacted_at,
        replied_at=lead.replied_at,
        url=lead.url,
    )
