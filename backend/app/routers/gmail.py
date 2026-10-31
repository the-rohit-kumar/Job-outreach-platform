"""Gmail connection (OAuth only) + reply detection endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..config import settings
from ..db import get_db
from ..deps import get_current_user
from ..models import Setting
from ..services import followups, gmail
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/gmail", tags=["gmail"], dependencies=[Depends(get_current_user)])


class ConnectOut(BaseModel):
    auth_url: str


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict:
    row = db.get(Setting, "gmail.address")
    return {
        "connected": gmail.is_connected(db),
        "address": str(row.value or "") if row else "",
        "client_id_configured": bool(settings.google_oauth_client_id),
        "scopes": gmail.SCOPES,
    }


@router.get("/auth-url", response_model=ConnectOut)
def auth_url(request: Request, db: Session = Depends(get_db)) -> ConnectOut:
    if not settings.google_oauth_client_id:
        raise HTTPException(
            status_code=400,
            detail="GOOGLE_OAUTH_CLIENT_ID is not set. Create Desktop-app OAuth credentials "
            "in Google Cloud Console and put them in .env.",
        )
    redirect = str(request.url_for("oauth_callback"))
    return ConnectOut(auth_url=gmail.build_auth_url(db, redirect))


@router.get("/oauth/callback", name="oauth_callback")
def oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    from fastapi.responses import RedirectResponse

    if error or not code:
        return RedirectResponse(f"{settings.app_url}/settings?gmail=error&reason={error or 'no_code'}")
    try:
        gmail.exchange_code(db, code, str(settings.google_oauth_redirect_uri), state)
    except gmail.GmailError as exc:
        return RedirectResponse(f"{settings.app_url}/settings?gmail=error&reason={exc}")
    return RedirectResponse(f"{settings.app_url}/settings?gmail=connected")


@router.post("/disconnect")
def disconnect(db: Session = Depends(get_db)) -> dict:
    gmail.disconnect(db)
    return {"connected": False}


@router.post("/check-replies")
def check_replies(db: Session = Depends(get_db)) -> dict:
    if not gmail.is_connected(db):
        raise HTTPException(status_code=400, detail="Gmail is not connected")
    found = gmail.fetch_replies(db)
    applied = followups.apply_inbound_messages(db)
    return {**found, **applied}
