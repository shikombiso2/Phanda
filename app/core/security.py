"""Auth primitives: JWT access tokens, password hashing, and refresh-token secrets.

Session model is short-lived access token + revocable refresh token, replacing
the previous single long-lived JWT that acted as both. See ``app/auth/`` for
the endpoints that issue and rotate these.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.models import User

bearer = HTTPBearer(auto_error=False)
_password_hasher = PasswordHasher()

# A short denylist of passwords common enough that allowing them defeats the
# point of requiring one. Not a substitute for length/complexity, which
# `validate_password_strength` also checks — just the cheapest possible
# guard against the handful of strings every credential-stuffing list tries
# first.
_COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789", "qwerty123",
    "letmein1", "welcome1", "iloveyou", "admin123", "changeme", "phanda123",
}


class WeakPasswordError(ValueError):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_password_strength(password: str, *, email: str | None = None) -> None:
    if len(password) < 10:
        raise WeakPasswordError("Password must be at least 10 characters long")
    if len(password) > 128:
        raise WeakPasswordError("Password is too long")
    if password.lower() in _COMMON_PASSWORDS:
        raise WeakPasswordError("That password is too common — please choose another")
    if email and password.lower() == normalize_email(email).split("@")[0]:
        raise WeakPasswordError("Password must not be the same as your email address")


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        # A corrupt or foreign-format hash must fail closed, not raise past login.
        return False


def needs_rehash(password_hash: str) -> bool:
    """True if the hash was made with older/weaker parameters than current defaults."""
    return _password_hasher.check_needs_rehash(password_hash)


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def generate_refresh_token_secret() -> str:
    """A high-entropy opaque secret — 256 bits, urlsafe. Unlike a 6-digit OTP,
    this is never brute-forceable, so a plain (unsalted, unkeyed) hash of it
    is safe to store and compare: see `hash_refresh_token`."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        # HTTPBearer(auto_error=False) returns None instead of raising here --
        # for both a missing header and one using the wrong scheme -- so this
        # is the only place that decides the status code. It must be 401, not
        # HTTPBearer's default 403: an Android client's auth interceptor
        # refreshes and retries on 401, and a missing/expired token must take
        # that same path as an invalid one, not a different, unhandled one.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    settings = get_settings()
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            raise ValueError("not an access token")
        user_id = uuid.UUID(payload["sub"])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
