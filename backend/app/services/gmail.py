"""Gmail integration: OAuth (never passwords), send, and reply detection.

Tokens are stored encrypted at rest with a key derived from APP_SECRET.
Scopes are gmail.send + gmail.readonly (read-only is used to detect replies).
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

from ..config import settings
from ..models import Message, Profile, SendEvent, Setting, utcnow

logger = logging.getLogger("outreachhub.gmail")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


class GmailError(RuntimeError):
    pass


class GmailNotConnected(GmailError):
    pass


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.app_secret.encode()).digest())
    return Fernet(key)


def _get_setting(db, key: str, default=None):
    row = db.get(Setting, key)
    return default if row is None or row.value is None else row.value


def _set_setting(db, key: str, value) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value, updated_at=utcnow()))
    else:
        row.value = value
        row.updated_at = utcnow()
    db.commit()


def is_connected(db) -> bool:
    return bool(_get_setting(db, "gmail.connected", False)) and bool(
        _get_setting(db, "gmail.tokens")
    )


def build_auth_url(db, redirect_uri: str) -> str:
    state = secrets.token_urlsafe(24)
    _set_setting(db, "gmail.oauth_state", state)
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": redirect_uri or settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code(
    db, code: str, redirect_uri: str, state: str | None = None, transport=None
) -> None:
    expected = _get_setting(db, "gmail.oauth_state")
    if state is None:
        state = _get_setting(db, "gmail.oauth_state")
    if expected and state != expected:
        raise GmailError("OAuth state mismatch - try connecting again.")
    data = {
        "code": code,
        "client_id": settings.google_oauth_client_id,
        "client_secret": settings.google_oauth_client_secret,
        "redirect_uri": redirect_uri or settings.google_oauth_redirect_uri,
        "grant_type": "authorization_code",
    }
    resp = httpx.Client(transport=transport, timeout=30.0).post(GOOGLE_TOKEN_URL, data=data)
    if resp.status_code != 200:
        raise GmailError(f"Token exchange failed: {resp.status_code} {resp.text[:200]}")
    payload = resp.json()
    _store_tokens(db, payload)
    _set_setting(db, "gmail.connected", True)
    _set_setting(db, "gmail.oauth_state", "")
    address = fetch_profile_email(db, transport=transport)
    if address:
        _set_setting(db, "gmail.address", address)


def _store_tokens(db, payload: dict) -> None:
    raw = json.dumps(payload).encode("utf-8")
    _set_setting(db, "gmail.tokens", _fernet().encrypt(raw).decode())


def _load_tokens(db) -> dict | None:
    encrypted = _get_setting(db, "gmail.tokens")
    if not encrypted:
        return None
    try:
        return json.loads(_fernet().decrypt(encrypted.encode()))
    except (InvalidToken, json.JSONDecodeError, ValueError):
        logger.error("Stored Gmail tokens are unreadable - reconnect required")
        return None


def disconnect(db) -> None:
    for key in ("gmail.connected", "gmail.tokens", "gmail.address"):
        row = db.get(Setting, key)
        if row is not None:
            row.value = False if key == "gmail.connected" else ""
            row.updated_at = utcnow()
    db.commit()


def _client(db, transport=None) -> httpx.Client:
    tokens = _refresh_if_needed(db, transport=transport)
    if not tokens:
        raise GmailNotConnected("Gmail is not connected")
    return httpx.Client(
        transport=transport,
        timeout=30.0,
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )


def _refresh_if_needed(db, transport=None) -> dict | None:
    tokens = _load_tokens(db)
    if not tokens:
        return None
    expires_at = float(tokens.get("expires_at", 0) or 0)
    now = datetime.now(timezone.utc).timestamp()
    if expires_at and now < expires_at - 60:
        return tokens
    if not tokens.get("refresh_token"):
        return tokens if expires_at > now else None
    data = {
        "client_id": settings.google_oauth_client_id,
        "client_secret": settings.google_oauth_client_secret,
        "refresh_token": tokens["refresh_token"],
        "grant_type": "refresh_token",
    }
    try:
        resp = httpx.Client(transport=transport, timeout=30.0).post(GOOGLE_TOKEN_URL, data=data)
        if resp.status_code != 200:
            raise GmailError(f"Refresh failed: {resp.status_code}")
        fresh = resp.json()
        tokens.update(fresh)
        tokens["expires_at"] = datetime.now(timezone.utc).timestamp() + int(
            fresh.get("expires_in", 3600)
        )
        _store_tokens(db, tokens)
        return tokens
    except (httpx.HTTPError, GmailError) as exc:
        logger.error("Gmail token refresh failed: %s", exc)
        return None


def fetch_profile_email(db, transport=None) -> str:
    try:
        with _client(db, transport=transport) as client:
            resp = client.get(f"{GMAIL_API}/profile")
            resp.raise_for_status()
            return resp.json().get("emailAddress", "")
    except GmailError:
        return ""
    except httpx.HTTPError:
        return ""


def send_email(db, to: str, subject: str, body: str, transport=None) -> dict:
    if not to:
        raise GmailError("No recipient address for this draft")
    message_id = secrets.token_urlsafe(8)
    headers = [
        f"To: {to}",
        f"Subject: {subject}",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        f"Message-ID: <{message_id}@outreachhub.local>",
    ]
    raw = "\r\n".join(headers) + "\r\n\r\n" + body
    encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode()
    with _client(db, transport=transport) as client:
        resp = client.post(
            f"{GMAIL_API}/messages/send",
            json={"raw": encoded},
        )
        if resp.status_code >= 400:
            raise GmailError(f"Gmail send failed: {resp.status_code} {resp.text[:200]}")
        data = resp.json()
    return {
        "id": data.get("id", ""),
        "thread_id": data.get("threadId", ""),
        "message_id": message_id,
    }


def fetch_replies(db, transport=None) -> dict:
    """Detect replies to our sends and record them as inbound messages."""
    events = (
        db.query(SendEvent)
        .filter(
            SendEvent.status.in_(("sent", "confirmed")),
            SendEvent.provider == "gmail",
            SendEvent.sent_at.isnot(None),
        )
        .order_by(SendEvent.id.desc())
        .limit(200)
        .all()
    )
    found = 0
    with _client(db, transport=transport) as client:
        for event in events:
            if event.thread_id:
                found += _check_thread(db, client, event)
            elif event.recipient:
                found += _search_from(db, client, event)
    return {"replies_found": found}


def _own_addresses(db) -> set[str]:
    addresses = set()
    stored = _get_setting(db, "gmail.address", "")
    if stored:
        addresses.add(str(stored).lower())
    profile = db.get(Profile, 1)
    if profile and profile.email:
        addresses.add(profile.email.lower())
    return addresses


def _check_thread(db, client: httpx.Client, event: SendEvent) -> int:
    resp = client.get(f"{GMAIL_API}/threads/{event.thread_id}", params={"format": "metadata"})
    if resp.status_code != 200:
        return 0
    thread = resp.json()
    mine = _own_addresses(db)
    count = 0
    sent_at = event.sent_at
    if sent_at and sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    for msg in thread.get("messages", []):
        headers = {h.get("name", "").lower(): h.get("value", "") for h in msg.get("payload", {}).get("headers", [])}
        sender = headers.get("from", "")
        if any(addr in sender.lower() for addr in mine):
            continue
        internal = int(msg.get("internalDate", "0") or 0) / 1000
        if sent_at and internal and internal <= sent_at.timestamp():
            continue
        if _already_recorded(db, msg.get("id", "")):
            continue
        body = _extract_body(msg)
        db.add(
            Message(
                lead_id=_lead_for_recipient(db, event.recipient),
                draft_id=event.draft_id,
                direction="in",
                channel=event.channel,
                body=body[:8000],
                sender=sender,
                gmail_message_id=msg.get("id", ""),
                received_at=datetime.fromtimestamp(internal, tz=timezone.utc)
                if internal
                else utcnow(),
                raw={"snippet": msg.get("snippet", "")},
            )
        )
        count += 1
    if count:
        db.commit()
    return count


def _search_from(db, client: httpx.Client, event: SendEvent) -> int:
    resp = client.get(
        f"{GMAIL_API}/messages",
        params={"q": f"from:{event.recipient} newer_than:14d", "maxResults": 5},
    )
    if resp.status_code != 200:
        return 0
    count = 0
    for item in resp.json().get("messages", []):
        if _already_recorded(db, item.get("id", "")):
            continue
        detail = client.get(
            f"{GMAIL_API}/messages/{item.get('id')}", params={"format": "metadata"}
        )
        if detail.status_code != 200:
            continue
        msg = detail.json()
        headers = {h.get("name", "").lower(): h.get("value", "") for h in msg.get("payload", {}).get("headers", [])}
        mine = _own_addresses(db)
        if any(addr in headers.get("from", "").lower() for addr in mine):
            continue
        internal = int(msg.get("internalDate", "0") or 0) / 1000
        db.add(
            Message(
                lead_id=_lead_for_recipient(db, event.recipient),
                draft_id=event.draft_id,
                direction="in",
                channel=event.channel,
                body=_extract_body(msg)[:8000],
                sender=headers.get("from", ""),
                gmail_message_id=msg.get("id", ""),
                received_at=datetime.fromtimestamp(internal, tz=timezone.utc)
                if internal
                else utcnow(),
                raw={"snippet": msg.get("snippet", "")},
            )
        )
        count += 1
    if count:
        db.commit()
    return count


def _already_recorded(db, gmail_message_id: str) -> bool:
    if not gmail_message_id:
        return False
    return db.query(Message).filter(Message.gmail_message_id == gmail_message_id).first() is not None


def _lead_for_recipient(db, recipient: str):
    if not recipient:
        return None
    from ..models import Lead

    for lead in db.query(Lead).filter(Lead.contacted_at.isnot(None)).limit(500).all():
        email = str((lead.contact or {}).get("email", "")).lower()
        if email and email == recipient.lower():
            return lead.id
    return None


def _extract_body(msg: dict) -> str:
    payload = msg.get("payload", {})
    parts = payload.get("parts") or [payload]
    for part in parts:
        if part.get("mimeType") in ("text/plain", "text/html"):
            data = part.get("body", {}).get("data", "")
            if data:
                try:
                    return base64.urlsafe_b64decode(data.encode()).decode("utf-8", "replace")
                except Exception:  # noqa: BLE001
                    pass
    return msg.get("snippet", "")
