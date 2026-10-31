from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..schemas import MessageOut, OnboardingItemOut, OnboardingPatchIn
from ..services import onboarding as onboarding_service

router = APIRouter(
    prefix="/api/onboarding", tags=["onboarding"], dependencies=[Depends(get_current_user)]
)


@router.get("", response_model=list[OnboardingItemOut])
def list_items(db: Session = Depends(get_db)) -> list:
    return onboarding_service.checklist(db)


@router.patch("/{key}", response_model=OnboardingItemOut)
def update_item(key: str, body: OnboardingPatchIn, db: Session = Depends(get_db)):
    item = onboarding_service.set_done(db, key, body.done)
    if item is None:
        raise HTTPException(status_code=404, detail="Unknown checklist item")
    return item


@router.post("/reset", response_model=MessageOut)
def reset(db: Session = Depends(get_db)) -> MessageOut:
    """Reset the manual (non-auto) items - handy when re-running onboarding."""
    items = onboarding_service.checklist(db)
    for item in items:
        if not item.auto:
            item.done = False
    db.commit()
    return MessageOut(message=f"Reset {sum(1 for i in items if not i.auto)} manual items")
