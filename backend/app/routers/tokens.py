"""API tokens for the Chrome extension and scripts. Shown once, stored hashed."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import ApiToken, utcnow
from ..schemas import MessageOut, TokenCreateIn, TokenCreatedOut, TokenOut
from ..security import issue_token

router = APIRouter(prefix="/api/tokens", tags=["tokens"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[TokenOut])
def list_tokens(db: Session = Depends(get_db)) -> list[ApiToken]:
    return db.query(ApiToken).order_by(ApiToken.created_at.desc()).all()


@router.post("", response_model=TokenCreatedOut)
def create_token(body: TokenCreateIn, db: Session = Depends(get_db)) -> TokenCreatedOut:
    row, raw = issue_token(db, body.name.strip())
    return TokenCreatedOut(token=TokenOut.model_validate(row), raw_token=raw)


@router.delete("/{token_id}", response_model=MessageOut)
def revoke_token(token_id: int, db: Session = Depends(get_db)) -> MessageOut:
    row = db.get(ApiToken, token_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Token not found")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        db.commit()
    return MessageOut(message="Token revoked")
