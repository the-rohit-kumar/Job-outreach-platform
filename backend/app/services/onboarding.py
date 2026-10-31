"""Onboarding checklist logic.

Each item can be auto-derived from real app state (preferred) or toggled
manually. Returning None means "fall back to the stored manual flag".
Later steps fill in the derivations as their features land.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from ..models import ApiToken, OnboardingItem, Profile, Setting


def _table_exists(db: Session, name: str) -> bool:
    try:
        return sa_inspect(db.get_bind()).has_table(name)
    except Exception:
        return False


def _setting(db: Session, key: str, default=None):
    row = db.get(Setting, key)
    return default if row is None else row.value


def derive(db: Session, key: str) -> bool | None:
    if key == "profile":
        profile = db.get(Profile, 1)
        if profile is None:
            return False
        return bool(
            profile.display_name.strip()
            and len(profile.about_me.strip()) >= 80
            and len(profile.do_not_mention) > 0
        )

    if key == "gmail":
        return bool(_setting(db, "gmail.connected", False))

    if key == "sources":
        try:
            from ..models import Collector

            return db.query(Collector).filter(Collector.enabled.is_(True)).count() > 0
        except Exception:
            return None

    if key == "extension":
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        return (
            db.query(ApiToken)
            .filter(ApiToken.revoked_at.is_(None), ApiToken.last_used_at.isnot(None))
            .count()
            > 0
        )

    if key == "first_review":
        try:
            from ..models import Draft

            return db.query(Draft).filter(Draft.reviewed_at.isnot(None)).count() > 0
        except Exception:
            return None

    return None


def checklist(db: Session) -> list[OnboardingItem]:
    items = db.query(OnboardingItem).order_by(OnboardingItem.order_index).all()
    for item in items:
        if item.auto:
            derived = derive(db, item.key)
            if derived is not None and derived != item.done:
                item.done = derived
    db.commit()
    return items


def set_done(db: Session, key: str, done: bool) -> OnboardingItem | None:
    item = db.get(OnboardingItem, key)
    if item is None:
        return None
    if item.auto:
        derived = derive(db, key)
        if derived is not None:
            item.done = derived
            db.commit()
            return item
    item.done = done
    db.commit()
    db.refresh(item)
    return item
