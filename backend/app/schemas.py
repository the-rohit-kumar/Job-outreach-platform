"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth -------------------------------------------------------------------
class SetupIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=200)

    @field_validator("username")
    @classmethod
    def _clean_username(cls, v: str) -> str:
        v = v.strip().lower()
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("username may only contain letters, numbers, - and _")
        return v


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(ORMModel):
    id: int
    username: str
    created_at: datetime


class AuthStatusOut(BaseModel):
    needs_setup: bool
    user: UserOut | None = None


# --- profile ----------------------------------------------------------------
class ProfileOut(ORMModel):
    id: int
    display_name: str
    email: str
    location: str
    github_url: str = ""
    cv_url: str = ""
    portfolio_url: str = ""
    about_me: str
    skills: list[str]
    do_not_mention: list[str]
    tone: dict
    updated_at: datetime


class ProfileIn(BaseModel):
    display_name: str = ""
    email: str = ""
    location: str = ""
    github_url: str = ""
    cv_url: str = ""
    portfolio_url: str = ""
    about_me: str = ""
    skills: list[str] = []
    do_not_mention: list[str] = []
    tone: dict = {}



# --- onboarding -------------------------------------------------------------
class OnboardingItemOut(ORMModel):
    key: str
    label: str
    href: str
    order_index: int
    auto: bool
    done: bool


class OnboardingPatchIn(BaseModel):
    done: bool


# --- tokens -----------------------------------------------------------------
class TokenCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TokenOut(ORMModel):
    id: int
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class TokenCreatedOut(BaseModel):
    token: TokenOut
    raw_token: str
    warning: str = "Copy this token now. It is shown only once and stored hashed."


# --- generic ----------------------------------------------------------------
class HealthOut(BaseModel):
    status: str
    app: str
    time: datetime


class MessageOut(BaseModel):
    message: str
