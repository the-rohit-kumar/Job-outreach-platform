"""Chrome extension API (assisted manual mode only).

The extension never navigates, clicks, scrolls or extracts in bulk. It only:
- captures the page YOU opened,
- logs a fill action (pace-limited),
- records that YOU pressed Send.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Draft, ExtensionAction, Lead, Setting, utcnow
from ..services import sending, warmup
from ..services.leads import upsert_lead

router = APIRouter(prefix="/api/extension", tags=["extension"])

MIN_FILL_INTERVAL_SECONDS = 20


class CaptureIn(BaseModel):
    platform: str = Field(min_length=2, max_length=32)
    url: str = ""
    name: str = ""
    headline: str = ""
    company: str = ""
    post_text: str = ""
    source: str = ""


class FillLogIn(BaseModel):
    platform: str
    draft_id: int | None = None


class ConfirmIn(BaseModel):
    platform: str
    draft_id: int | None = None
    lead_id: int | None = None


class WarningIn(BaseModel):
    platform: str
    kind: str = "captcha"


@router.get("/ping")
def ping(user=Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Called by the extension to verify its token."""
    from ..config import settings

    return {
        "ok": True,
        "app": settings.app_name,
        "api_url": settings.api_url,
        "user": user.username,
    }


@router.post("/capture")
def capture(
    body: CaptureIn,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    text = " ".join(x for x in [body.post_text, body.headline, body.company] if x).strip()
    if not text:
        raise HTTPException(status_code=422, detail="Nothing visible to capture on this page")
    platform = body.platform.lower()
    lead, outcome = upsert_lead(
        db,
        {
            "source": body.source or f"manual:{platform}",
            "title": (body.headline or body.post_text[:120] or f"{platform} post")[:255],
            "company": body.company,
            "url": body.url,
            "description": body.post_text[:8000],
            "raw_text": text[:8000],
            "remote": True,
            "contact": {
                "name": body.name,
                "profile_url": body.url,
                "platform": platform,
            },
        },
    )
    _ledger(db, platform, "capture", detail=body.url[:200])
    if outcome == "suppressed":
        return {"ok": False, "reason": "suppressed", "lead_id": None}
    if outcome == "duplicate":
        return {"ok": True, "outcome": "duplicate", "lead_id": lead.id if lead else None}
    return {"ok": True, "outcome": "created", "lead_id": lead.id if lead else None}


@router.get("/status")
def status(platform: str = "other", db: Session = Depends(get_db)) -> dict:
    cap = warmup.platform_daily_cap(db, platform)
    used = warmup.platform_sent_today(db, platform)
    last_fill = (
        db.query(ExtensionAction)
        .filter(ExtensionAction.platform == platform, ExtensionAction.action == "fill")
        .order_by(ExtensionAction.id.desc())
        .first()
    )
    last_fill_ts = last_fill.ts if last_fill else None
    wait_seconds = 0
    if last_fill_ts is not None:
        ts = last_fill_ts if last_fill_ts.tzinfo else last_fill_ts.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - ts).total_seconds()
        wait_seconds = max(0, MIN_FILL_INTERVAL_SECONDS - int(elapsed))
    paused_until = _pause_until(db, platform)
    return {
        "platform": platform,
        "cap": cap,
        "used": used,
        "remaining": max(0, cap - used),
        "seconds_until_next_fill": wait_seconds,
        "paused_until": paused_until,
        "min_fill_interval_seconds": MIN_FILL_INTERVAL_SECONDS,
    }


@router.get("/pending")
def pending(platform: str, url: str = "", db: Session = Depends(get_db)) -> dict:
    """Approved draft waiting to be pasted into the open message box."""
    query = (
        db.query(Draft)
        .join(Lead, Draft.lead_id == Lead.id)
        .filter(Draft.status == "approved", Lead.opted_out.is_(False))
    )
    if url:
        from ..services.leads import url_hash

        query = query.filter(Lead.url_hash == url_hash(url))
    draft = query.order_by(Draft.id.desc()).first()
    if draft is None:
        return {"ok": False, "reason": "no approved draft for this page"}
    lead = db.get(Lead, draft.lead_id)
    return {
        "ok": True,
        "draft": {
            "id": draft.id,
            "lead_id": draft.lead_id,
            "variant": draft.variant,
            "channel": draft.channel,
            "subject": draft.subject,
            "body": draft.body,
            "chars": len(draft.body or ""),
        },
        "lead": {
            "id": lead.id if lead else None,
            "company": lead.company if lead else "",
            "title": lead.title if lead else "",
            "score": lead.score if lead else None,
        },
    }


@router.post("/fill-log")
def fill_log(body: FillLogIn, db: Session = Depends(get_db)) -> dict:
    """Human-pace gate: 20s between fills, daily cap per platform."""
    status_info = status(body.platform, db)
    if status_info["paused_until"]:
        raise HTTPException(
            status_code=429,
            detail=f"Stopped: restriction notice on {body.platform} until {status_info['paused_until']}. "
            "Take a break (24-48h) and halve the cap.",
        )
    if status_info["seconds_until_next_fill"] > 0:
        raise HTTPException(
            status_code=429,
            detail=f"Wait {status_info['seconds_until_next_fill']}s between fills (human pace).",
        )
    if status_info["remaining"] <= 0:
        raise HTTPException(
            status_code=429,
            detail=f"Daily cap of {status_info['cap']} reached for {body.platform}. Stop for today.",
        )
    _ledger(db, body.platform, "fill", detail=f"draft:{body.draft_id or '-'}")
    return {"ok": True, **status_info, "used": status_info["used"] + 1}


@router.post("/confirm")
def confirm(body: ConfirmIn, db: Session = Depends(get_db)) -> dict:
    """You pressed Send in the real site; we only update the tracker."""
    try:
        result = sending.confirm_platform_send(
            db, draft_id=body.draft_id, lead_id=body.lead_id, platform=body.platform
        )
    except sending.SendBlocked as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _ledger(db, body.platform, "confirm", detail=f"draft:{body.draft_id or '-'}")
    info = status(body.platform, db)
    return {**result, "used": info["used"], "cap": info["cap"]}


@router.post("/warning")
def warning(body: WarningIn, db: Session = Depends(get_db)) -> dict:
    """Captcha/restriction seen in the page -> stop that platform for 24h."""
    until = datetime.now(timezone.utc) + timedelta(hours=24)
    key = f"extension.pause.{body.platform}"
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=until.isoformat(), updated_at=utcnow()))
    else:
        row.value = until.isoformat()
        row.updated_at = utcnow()
    db.commit()
    _ledger(db, body.platform, "warning", detail=body.kind)
    return {"ok": True, "paused_until": until.isoformat()}


def _ledger(db: Session, platform: str, action: str, detail: str = "") -> None:
    db.add(
        ExtensionAction(
            platform=platform, action=action, day_key=warmup.day_key(), detail=detail[:255]
        )
    )
    db.commit()


def _pause_until(db: Session, platform: str) -> str | None:
    row = db.get(Setting, f"extension.pause.{platform}")
    if row is None or not row.value:
        return None
    try:
        until = datetime.fromisoformat(str(row.value))
    except ValueError:
        return None
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    if until <= datetime.now(timezone.utc):
        return None
    return until.isoformat()
