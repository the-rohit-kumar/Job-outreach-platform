"""Password hashing and API token helpers. We never store raw secrets."""
from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .models import ApiToken

_hasher = PasswordHasher(time_cost=2, memory_cost=64 * 1024, parallelism=2)
TOKEN_PREFIX = "oh_"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def new_api_token() -> tuple[str, str, str]:
    """Return (raw_token, sha256_hash, display_prefix). Raw is shown once only."""
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return raw, hash_token(raw), raw[:11]


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_token(db, name: str) -> tuple[ApiToken, str]:
    from .models import utcnow

    raw, token_hash, prefix = new_api_token()
    row = ApiToken(name=name, token_hash=token_hash, prefix=prefix, created_at=utcnow())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, raw


def lookup_token(db, raw: str) -> ApiToken | None:
    if not raw:
        return None
    row = (
        db.query(ApiToken)
        .filter(ApiToken.token_hash == hash_token(raw), ApiToken.revoked_at.is_(None))
        .one_or_none()
    )
    if row is not None:
        from .models import utcnow

        row.last_used_at = utcnow()
        db.commit()
    return row
