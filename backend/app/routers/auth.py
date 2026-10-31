"""Login / setup / logout. Single user, local accounts only.

We never ask for LinkedIn, X, Wellfound or Gmail passwords anywhere in the
app - those are logged into by you in your own browser.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import get_current_user, optional_user
from ..models import User, utcnow
from ..schemas import AuthStatusOut, LoginIn, MessageOut, SetupIn, UserOut
from ..security import hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _start_session(request: Request, user: User) -> None:
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["logged_in_at"] = utcnow().isoformat()


@router.get("/status", response_model=AuthStatusOut)
def auth_status(request: Request, db: Session = Depends(get_db)) -> AuthStatusOut:
    has_users = db.query(User).count() > 0
    if not has_users:
        return AuthStatusOut(needs_setup=True, user=None)
    user = optional_user(request, db)
    return AuthStatusOut(
        needs_setup=False,
        user=UserOut.model_validate(user) if user is not None else None,
    )


@router.post("/setup", response_model=UserOut)
def first_run_setup(
    body: SetupIn, request: Request, response: Response, db: Session = Depends(get_db)
) -> User:
    if db.query(User).count() > 0:
        raise HTTPException(status_code=409, detail="A login already exists. Use sign in.")
    if len(body.password) < settings.min_password_length:
        raise HTTPException(status_code=422, detail="Password is too short")
    user = User(username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    _start_session(request, user)
    return user


@router.post("/login", response_model=UserOut)
def login(
    body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)
) -> User:
    user = db.query(User).filter(User.username == body.username.strip().lower()).one_or_none()
    if user is None or not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong username or password")
    user.last_login_at = utcnow()
    db.commit()
    _start_session(request, user)
    return user


@router.post("/logout", response_model=MessageOut)
def logout(request: Request) -> MessageOut:
    request.session.clear()
    return MessageOut(message="Signed out")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
