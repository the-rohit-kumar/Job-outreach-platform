"""Warm-up schedule, daily caps, send window, spacing and auto-pause rules.

All limits are computed from real send history - no hidden state.
"""
from __future__ import annotations

import random
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import SendEvent, Setting, utcnow

DAY_KEY = "%Y-%m-%d"


def day_key(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime(DAY_KEY)


def _get(db: Session, key: str, default=None):
    row = db.get(Setting, key)
    return default if row is None or row.value is None else row.value


def warmup_start(db: Session) -> datetime:
    raw = _get(db, "warmup.started_at")
    if raw:
        try:
            value = datetime.fromisoformat(str(raw))
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    first = (
        db.query(func.min(SendEvent.sent_at))
        .filter(SendEvent.status.in_(("sent", "confirmed")))
        .scalar()
    )
    if first is not None:
        return first if first.tzinfo else first.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def warmup_day(db: Session) -> int:
    start = warmup_start(db)
    return max(1, (datetime.now(timezone.utc) - start).days + 1)


def ramp_email_cap(day: int) -> int:
    if day <= 3:
        return 10
    if day <= 7:
        return 20
    if day <= 14:
        return 30
    return 50


def ramp_platform_cap(day: int) -> int:
    if day <= 3:
        return 5
    if day <= 7:
        return 10
    return 25


def email_daily_cap(db: Session) -> int:
    configured = int(_get(db, "warmup.email_daily_cap", 50) or 50)
    return max(1, min(ramp_email_cap(warmup_day(db)), configured))


def platform_daily_cap(db: Session, platform: str | None = None) -> int:
    configured = int(_get(db, "warmup.platform_daily_cap", 25) or 25)
    base = max(1, min(ramp_platform_cap(warmup_day(db)), configured))
    if platform:
        per_platform = int(_get(db, f"warmup.platform_cap.{platform}", base) or base)
        base = min(base, per_platform)
    return base


def sent_today(db: Session, channel: str = "email") -> int:
    return (
        db.query(func.count(SendEvent.id))
        .filter(
            SendEvent.day_key == day_key(),
            SendEvent.channel == channel,
            SendEvent.status.in_(("queued", "sent", "confirmed")),
        )
        .scalar()
        or 0
    )


def platform_sent_today(db: Session, platform: str) -> int:
    return (
        db.query(func.count(SendEvent.id))
        .filter(
            SendEvent.day_key == day_key(),
            SendEvent.channel == "platform",
            SendEvent.note == platform,
            SendEvent.status.in_(("queued", "sent", "confirmed")),
        )
        .scalar()
        or 0
    )


def bounce_rate(db: Session, window: int = 30) -> float:
    rows = (
        db.query(SendEvent)
        .filter(SendEvent.status.in_(("sent", "confirmed")), SendEvent.sent_at.isnot(None))
        .order_by(SendEvent.id.desc())
        .limit(window)
        .all()
    )
    if len(rows) < 10:
        return 0.0
    bounces = sum(1 for r in rows if r.bounce)
    return bounces / len(rows)


def spam_signal_present(db: Session) -> bool:
    return (
        db.query(func.count(SendEvent.id))
        .filter(SendEvent.spam_signal.is_(True))
        .order_by(SendEvent.id.desc())
        .limit(10)
        .scalar()
        or 0
    ) > 0


def pause_state(db: Session) -> tuple[bool, str]:
    """(paused, reason). Never override silently - find the cause instead."""
    if bool(_get(db, "send.paused", False)):
        return True, "Sending is paused in Settings."
    rate = bounce_rate(db)
    limit = float(_get(db, "send.pause_bounce_rate", 0.05))
    if rate > limit:
        return True, f"Bounce rate {rate:.0%} is over the {limit:.0%} limit."
    if spam_signal_present(db):
        return True, "A spam signal was recorded on a recent send."
    return False, ""


def window_bounds(db: Session) -> tuple[time, time]:
    start = str(_get(db, "send.window_start", "09:00"))
    end = str(_get(db, "send.window_end", "18:00"))
    try:
        sh, sm = (int(x) for x in start.split(":"))
        eh, em = (int(x) for x in end.split(":"))
    except (ValueError, AttributeError):
        sh, sm, eh, em = 9, 0, 18, 0
    return time(sh, sm), time(eh, em)


def window_open(db: Session, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    local = now.astimezone()  # send window is expressed in your local time
    start, end = window_bounds(db)
    return start <= local.time() <= end


def spacing_minutes(db: Session) -> float:
    low = float(_get(db, "send.spacing_minutes_min", 3))
    high = float(_get(db, "send.spacing_minutes_max", 8))
    if high < low:
        high = low
    return random.uniform(low, high)


def last_email_sent_at(db: Session) -> datetime | None:
    value = (
        db.query(func.max(SendEvent.sent_at))
        .filter(SendEvent.channel == "email", SendEvent.status.in_(("sent", "confirmed")))
        .scalar()
    )
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def next_send_time(db: Session) -> datetime:
    """Earliest time the next email may go out (spacing + window aware)."""
    last = last_email_sent_at(db)
    candidate = datetime.now(timezone.utc)
    if last is not None:
        candidate = max(candidate, last + timedelta(minutes=spacing_minutes(db)))
    if not window_open(db, candidate):
        start, _ = window_bounds(db)
        local = candidate.astimezone()
        today_start = datetime.combine(local.date(), start, tzinfo=local.tzinfo).astimezone(
            timezone.utc
        )
        if today_start > candidate:
            candidate = today_start
        else:
            tomorrow = (local + timedelta(days=1)).date()
            candidate = datetime.combine(tomorrow, start, tzinfo=local.tzinfo).astimezone(
                timezone.utc
            )
    return candidate


def email_status(db: Session) -> dict:
    cap = email_daily_cap(db)
    used = sent_today(db, "email")
    paused, reason = pause_state(db)
    rate = bounce_rate(db)
    return {
        "day": warmup_day(db),
        "cap": cap,
        "used": used,
        "remaining": max(0, cap - used),
        "paused": paused,
        "pause_reason": reason,
        "bounce_rate": round(rate, 4),
        "window_open": window_open(db),
        "next_send_at": next_send_time(db).isoformat() if not paused else None,
        "first_send_at": warmup_start(db).isoformat(),
    }


def platform_status(db: Session, platforms: list[str] | None = None) -> dict:
    platforms = platforms or ["linkedin", "x", "wellfound", "discord", "other"]
    out = {}
    for platform in platforms:
        cap = platform_daily_cap(db, platform)
        used = platform_sent_today(db, platform)
        out[platform] = {"cap": cap, "used": used, "remaining": max(0, cap - used)}
    return out
