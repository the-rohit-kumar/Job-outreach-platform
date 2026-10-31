"""Shared FastAPI dependencies: current user (cookie session or bearer token)."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .security import lookup_token


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Accepts either the login session cookie (web app) or an API token
    (Chrome extension / scripts). Passwords are never involved here."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        raw = auth_header[7:].strip()
        token = lookup_token(db, raw)
        if token is None:
            raise _unauthorized()
        user = db.query(User).first()
        if user is None:
            raise _authorized_user_missing()
        return user

    user_id = request.session.get("user_id")
    if user_id:
        user = db.get(User, user_id)
        if user is not None:
            return user
    raise _unauthorized()


def _authorized_user_missing() -> HTTPException:
    return HTTPException(status_code=401, detail="No user is set up yet")


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    try:
        return get_current_user(request, db)
    except HTTPException:
        return None
