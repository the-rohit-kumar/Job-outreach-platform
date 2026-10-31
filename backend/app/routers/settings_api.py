"""Settings API: targets, warm-up, window, caps, pause, suppression, LLM usage."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Lead, Setting, Suppression, UsageEvent, utcnow
from ..services import warmup

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(get_current_user)])

# key -> (type, tooltip). Tooltips explain the safe default and why it exists.
SETTING_DEFS: dict[str, tuple[str, str]] = {
    "daily.target_collected": (
        "int",
        "Safe default 300/day. Volume only matters if quality stays up; lower it if review takes longer than 30 minutes.",
    ),
    "daily.target_qualified": (
        "int",
        "Safe default 100/day. Qualifying is cheap (a fast model scores them); drafting is the bottleneck.",
    ),
    "daily.target_drafts": (
        "int",
        "Safe default 50 drafts so 30-40 survive your review. More drafts means more skim-reading, not more replies.",
    ),
    "daily.target_sent": (
        "int",
        "Safe default 35. Cold outreach reply rates fall when daily volume jumps faster than warm-up allows.",
    ),
    "warmup.email_daily_cap": (
        "int",
        "Safe default 50 (the ceiling). The warm-up ramp still limits you: 10/day for days 1-3, 20 for 4-7, 30 for 8-14, then this ceiling. Sending fast from a new domain gets you flagged.",
    ),
    "warmup.platform_daily_cap": (
        "int",
        "Safe default 25 per platform, never higher. Platforms restrict accounts that message in bursts; the ramp starts at 5-10.",
    ),
    "send.window_start": (
        "str",
        "Safe default 09:00 (your local time). Mail that lands at 3am reads as automated.",
    ),
    "send.window_end": (
        "str",
        "Safe default 18:00. Nothing leaves the app outside this window, so replies arrive when you can answer them.",
    ),
    "send.spacing_minutes_min": (
        "int",
        "Safe default 3 minutes. Human-paced gaps are the cheapest spam-signal protection there is.",
    ),
    "send.spacing_minutes_max": (
        "int",
        "Safe default 8 minutes. Randomized spacing between min and max so timing never looks mechanical.",
    ),
    "send.pause_bounce_rate": (
        "float",
        "Safe default 0.05 (5%). Above that the app pauses itself: fix the list instead of burning the domain.",
    ),
    "send.paused": (
        "bool",
        "Manual pause. Use it when you see a spam or platform warning; the app also pauses on its own.",
    ),
    "scoring.threshold": (
        "int",
        "Safe default 60. Below this a lead is filtered out; raise it if drafts feel off-target, lower it if too few qualify.",
    ),
    "dedupe.cooldown_days": (
        "int",
        "Safe default 60. One contact per company per window - contacting the same startup three times looks desperate.",
    ),
    "llm.spend_cap_usd": (
        "float",
        "Safe default $5/day. The app refuses further LLM calls once hit, so a bad loop cannot empty your wallet.",
    ),
}


class SettingItem(BaseModel):
    key: str
    value: object = None
    type: str = "str"
    tooltip: str = ""


class SettingsPut(BaseModel):
    values: dict = Field(default_factory=dict)


class SuppressionIn(BaseModel):
    kind: str = "email"
    value: str
    reason: str = ""


class SuppressionOut(BaseModel):
    id: int
    kind: str
    value: str
    reason: str
    source: str
    created_at: datetime


def _typed(raw, type_name: str):
    if raw is None:
        return None
    try:
        if type_name == "int":
            return int(raw)
        if type_name == "float":
            return float(raw)
        if type_name == "bool":
            return bool(raw)
    except (TypeError, ValueError):
        return None
    return raw


@router.get("")
def get_settings(db: Session = Depends(get_db)) -> dict:
    rows = {r.key: r.value for r in db.query(Setting).all()}
    items = [
        SettingItem(
            key=key,
            value=rows.get(key),
            type=type_name,
            tooltip=tooltip,
        )
        for key, (type_name, tooltip) in SETTING_DEFS.items()
    ]
    return {
        "settings": items,
        "warmup": warmup.email_status(db),
        "platform_warmup": warmup.platform_status(db),
        "llm": {
            "spend_today_usd": round(
                db.query(func.coalesce(func.sum(UsageEvent.cost_usd), 0.0))
                .filter(UsageEvent.day_key == warmup.day_key())
                .scalar()
                or 0.0,
                4,
            ),
            "cap_usd": float(rows.get("llm.spend_cap_usd") or 5.0),
            "calls_today": db.query(func.count(UsageEvent.id))
            .filter(UsageEvent.day_key == warmup.day_key())
            .scalar()
            or 0,
        },
        "raw": rows,
    }


@router.put("")
def put_settings(body: SettingsPut, db: Session = Depends(get_db)) -> dict:
    for key, value in body.values.items():
        type_name = SETTING_DEFS.get(key, ("str", ""))[0]
        if key in SETTING_DEFS:
            value = _typed(value, type_name)
            if value is None:
                raise HTTPException(status_code=422, detail=f"Invalid value for {key}")
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=value, updated_at=utcnow()))
        else:
            row.value = value
            row.updated_at = utcnow()
    db.commit()
    return {"ok": True, "updated": list(body.values)}


@router.get("/suppression", response_model=list[SuppressionOut])
def list_suppression(db: Session = Depends(get_db)) -> list[Suppression]:
    return db.query(Suppression).order_by(Suppression.id.desc()).limit(500).all()


@router.post("/suppression", response_model=SuppressionOut)
def add_suppression(body: SuppressionIn, db: Session = Depends(get_db)) -> Suppression:
    if body.kind not in ("email", "domain", "person", "url", "company"):
        raise HTTPException(status_code=422, detail="kind must be email|domain|person|url|company")
    value = body.value.strip().lower()
    if not value:
        raise HTTPException(status_code=422, detail="value is required")
    existing = (
        db.query(Suppression)
        .filter(Suppression.kind == body.kind, Suppression.value == value)
        .first()
    )
    if existing is not None:
        return existing
    row = Suppression(kind=body.kind, value=value, reason=body.reason, source="manual")
    db.add(row)
    db.commit()
    db.refresh(row)
    if body.kind == "email":
        _suppress_matching_leads(db, email=value)
    elif body.kind == "domain":
        _suppress_matching_leads(db, domain=value)
    elif body.kind == "person":
        _suppress_matching_leads(db, person=value)
    return row


@router.delete("/suppression/{row_id}")
def delete_suppression(row_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(Suppression, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


def _suppress_matching_leads(db: Session, *, email: str = "", domain: str = "", person: str = "") -> None:
    leads = db.query(Lead).filter(Lead.opted_out.is_(False)).limit(2000).all()
    for lead in leads:
        contact = lead.contact or {}
        hit = False
        if email and str(contact.get("email", "")).lower() == email:
            hit = True
        if domain and lead.company_domain == domain:
            hit = True
        if person and str(contact.get("name", "")).lower() == person:
            hit = True
        if hit:
            lead.opted_out = True
            lead.status = "suppressed"
            lead.updated_at = utcnow()
    db.commit()
