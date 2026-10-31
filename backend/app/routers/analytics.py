"""Analytics: reply rate by source, channel, variant, score band + weekly view."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Draft, Lead, Message, SendEvent

router = APIRouter(prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(get_current_user)])

POSITIVE_WORDS = [
    "interested", "sounds good", "sounds great", "let's talk", "lets talk", "call",
    "available", "rate", "send your", "next step", "yes", "sure", "would love",
    "schedule", "calendar", "trial", "start when", "can you start",
]
BANDS = [(0, 40, "0-40"), (41, 60, "41-60"), (61, 80, "61-80"), (81, 100, "81-100")]


def _positive_replies(db: Session) -> set[int]:
    lead_ids: set[int] = set()
    for msg in db.query(Message).filter(Message.direction == "in").all():
        if msg.lead_id is None:
            continue
        low = (msg.body or "").lower()
        if any(w in low for w in POSITIVE_WORDS):
            lead_ids.add(msg.lead_id)
    for lead in db.query(Lead).filter(Lead.stage.in_(("call", "trial_task", "won"))).all():
        lead_ids.add(lead.id)
    return lead_ids


@router.get("")
def analytics(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    positive = _positive_replies(db)

    contacted = (
        db.query(Lead).filter(Lead.contacted_at.isnot(None), Lead.contacted_at >= since).all()
    )
    replied_ids = {l.id for l in contacted if l.replied_at}

    def rate(rows: list[Lead]) -> dict:
        sent = len(rows)
        replies = len([r for r in rows if r.id in replied_ids])
        pos = len([r for r in rows if r.id in positive])
        return {
            "sent": sent,
            "replies": replies,
            "positive": pos,
            "reply_rate": round(replies / sent, 4) if sent else 0.0,
            "positive_rate": round(pos / sent, 4) if sent else 0.0,
        }

    by_source: dict[str, list[Lead]] = {}
    by_channel: dict[str, list[Lead]] = {}
    by_band: dict[str, list[Lead]] = {}
    for lead in contacted:
        by_source.setdefault(lead.source, []).append(lead)
        by_channel.setdefault(lead.channel, []).append(lead)
        band = next((label for lo, hi, label in BANDS if (lead.score or 0) >= lo and (lead.score or 0) <= hi), "0-40")
        by_band.setdefault(band, []).append(lead)

    by_variant = _by_variant(db, since, replied_ids, positive)
    weekly = _weekly(db, days=max(days, 28), replied_ids=replied_ids)

    overall = rate(contacted)
    ranking = sorted(
        [{"source": k, **rate(v)} for k, v in by_source.items()],
        key=lambda r: (-r["reply_rate"], -r["sent"]),
    )
    return {
        "window_days": days,
        "overall": overall,
        "by_source": [
            {"source": k, **rate(v)} for k, v in sorted(by_source.items(), key=lambda kv: kv[0])
        ],
        "by_channel": [{"channel": k, **rate(v)} for k, v in by_channel.items()],
        "by_variant": by_variant,
        "by_score_band": [
            {"band": label, **rate(by_band[label])} for _, _, label in reversed(BANDS)
            if label in by_band
        ],
        "weekly": weekly,
        "ranking": ranking,
        "recommendation": _recommendation(ranking, overall),
    }


def _by_variant(db: Session, since, replied_ids: set[int], positive: set[int]) -> list[dict]:
    rows = (
        db.query(Draft)
        .join(Lead, Draft.lead_id == Lead.id)
        .filter(
            Lead.contacted_at.isnot(None),
            Lead.contacted_at >= since,
            Draft.status.in_(("sent", "replied")),
        )
        .all()
    )
    grouped: dict[str, list[Draft]] = {}
    for draft in rows:
        grouped.setdefault(draft.variant, []).append(draft)
    out = []
    for variant, drafts in grouped.items():
        sent = len(drafts)
        replies = len({d.lead_id for d in drafts if d.lead_id in replied_ids})
        pos = len({d.lead_id for d in drafts if d.lead_id in positive})
        out.append(
            {
                "variant": variant,
                "sent": sent,
                "replies": replies,
                "positive": pos,
                "reply_rate": round(replies / sent, 4) if sent else 0.0,
                "positive_rate": round(pos / sent, 4) if sent else 0.0,
            }
        )
    return sorted(out, key=lambda r: r["variant"])


def _weekly(db: Session, *, days: int, replied_ids: set[int]) -> list[dict]:
    weeks: dict[str, dict] = {}
    today = datetime.now(timezone.utc).date()
    for offset in range(0, days // 7 + 1):
        end = today - timedelta(weeks=offset)
        start = end - timedelta(days=6)
        weeks[start.isoformat()] = {
            "week_start": start.isoformat(),
            "sent": 0,
            "replies": 0,
            "reply_rate": 0.0,
        }
    for lead in db.query(Lead).filter(Lead.contacted_at.isnot(None)).all():
        ct = lead.contacted_at
        if ct is None:
            continue
        ct = ct if ct.tzinfo else ct.replace(tzinfo=timezone.utc)
        date = ct.date()
        for key in weeks:
            start = datetime.fromisoformat(key).date()
            if start <= date <= start + timedelta(days=6):
                weeks[key]["sent"] += 1
                if lead.id in replied_ids:
                    weeks[key]["replies"] += 1
                break
    out = []
    for key in sorted(weeks, reverse=True):
        row = weeks[key]
        row["reply_rate"] = round(row["replies"] / row["sent"], 4) if row["sent"] else 0.0
        out.append(row)
    return out


def _recommendation(ranking: list[dict], overall: dict) -> str:
    if overall["sent"] < 20:
        return (
            "Not enough sends yet. Typical cold-outreach reply rate is 3-8%; "
            "keep collecting and reviewing before judging sources."
        )
    top = [r for r in ranking if r["sent"] >= 10 and r["reply_rate"] >= 0.03]
    weak = [r for r in ranking if r["sent"] >= 10 and r["reply_rate"] < 0.01]
    parts = []
    if top:
        parts.append("Double down on " + ", ".join(r["source"] for r in top[:3]) + ".")
    if weak:
        parts.append("Disable " + ", ".join(r["source"] for r in weak[:3]) + " (under 1% after 10+ sends).")
    if overall["reply_rate"] < 0.02 and overall["sent"] >= 40:
        parts.append(
            "Under 2% overall: the drafts need to be more specific, not more numerous."
        )
    return " ".join(parts) or "Keep going - compare sources again after 100+ messages."
