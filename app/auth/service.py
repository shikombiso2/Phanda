"""Registration, login, Google linking, and refresh-token lifecycle.

Kept separate from ``app/auth/router.py`` so the transaction and security
logic — which touches three tables (users, user_auth_identities,
refresh_tokens) — is unit-testable without going through HTTP.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.google import VerifiedGoogleIdentity
from app.auth.schemas import AuthTokensOut
from app.core.config import get_settings
from app.core.errors import api_error
from app.core.models import AuthProvider, Profile, RefreshToken, User, UserAuthIdentity
from app.core.observability import emit_event
from app.core.security import (
    WeakPasswordError,
    create_access_token,
    generate_refresh_token_secret,
    hash_password,
    hash_refresh_token,
    normalize_email,
    validate_password_strength,
    verify_password,
)
from fastapi import status


def register_with_password(db: Session, *, email: str, password: str) -> User:
    normalized = normalize_email(email)
    try:
        validate_password_strength(password, email=normalized)
    except WeakPasswordError as exc:
        raise api_error(status.HTTP_400_BAD_REQUEST, code="weak_password", message=str(exc)) from exc

    if db.scalar(select(User).where(User.email == normalized)):
        raise api_error(
            status.HTTP_409_CONFLICT, code="email_already_registered", message="An account with this email already exists."
        )

    user = User(email=normalized, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id))
    db.commit()
    db.refresh(user)
    emit_event("user_registered", user_id=user.id, method="password")
    return user


def authenticate_with_password(db: Session, *, email: str, password: str) -> User:
    normalized = normalize_email(email)
    invalid = api_error(status.HTTP_401_UNAUTHORIZED, code="invalid_credentials", message="Incorrect email or password.")
    user = db.scalar(select(User).where(User.email == normalized))
    # A missing user and a Google-only account (no password_hash) both fail
    # identically to the caller — revealing which would tell an attacker
    # whether an email is registered, and by which method.
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        raise invalid
    return user


def authenticate_or_create_with_google(db: Session, identity: VerifiedGoogleIdentity) -> tuple[User, bool]:
    normalized = normalize_email(identity.email)
    link = db.scalar(
        select(UserAuthIdentity).where(
            UserAuthIdentity.provider == AuthProvider.google, UserAuthIdentity.provider_subject == identity.subject
        )
    )
    if link:
        user = db.get(User, link.user_id)
        assert user is not None
        return user, False

    existing_user = db.scalar(select(User).where(User.email == normalized))
    if existing_user:
        if not identity.email_verified:
            # Linking by email match only makes sense if Google itself vouches
            # for that email. An unverified claim of someone else's address
            # must not silently attach a new sign-in method to their account.
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                code="google_email_not_verified",
                message="This Google account's email address is not verified.",
            )
        # Same person, previously registered by password (or a different
        # provider) — link Google to that account rather than creating a
        # second one for the same email.
        db.add(UserAuthIdentity(user_id=existing_user.id, provider=AuthProvider.google, provider_subject=identity.subject))
        if not existing_user.email_verified_at:
            existing_user.email_verified_at = datetime.now(timezone.utc)
        db.commit()
        emit_event("auth_identity_linked", user_id=existing_user.id, provider="google")
        return existing_user, False

    user = User(
        email=normalized,
        password_hash=None,
        email_verified_at=datetime.now(timezone.utc) if identity.email_verified else None,
    )
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id))
    db.add(UserAuthIdentity(user_id=user.id, provider=AuthProvider.google, provider_subject=identity.subject))
    db.commit()
    db.refresh(user)
    emit_event("user_registered", user_id=user.id, method="google")
    return user, True


@dataclass(frozen=True)
class _IssuedRefreshToken:
    id: uuid.UUID
    secret: str


def _issue_refresh_token(db: Session, user_id: uuid.UUID, *, rotated_from_id: uuid.UUID | None = None) -> _IssuedRefreshToken:
    settings = get_settings()
    secret = generate_refresh_token_secret()
    token = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(secret),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days),
        rotated_from_id=rotated_from_id,
    )
    db.add(token)
    db.flush()
    return _IssuedRefreshToken(id=token.id, secret=secret)


def issue_tokens(db: Session, user: User, *, is_new_user: bool) -> AuthTokensOut:
    settings = get_settings()
    refresh = _issue_refresh_token(db, user.id)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return AuthTokensOut(
        access_token=create_access_token(user.id),
        refresh_token=refresh.secret,
        expires_in=settings.access_token_minutes * 60,
        is_new_user=is_new_user,
    )


def _is_benign_concurrent_refresh(db: Session, token: RefreshToken, now: datetime) -> bool:
    """True when a second presentation of an already-rotated token is a racing
    client rather than an attacker.

    Three conditions, all required. Each one exists to stop the grace window
    resurrecting a session that was deliberately ended:

    1. Inside the window, measured from ``revoked_at`` -- the instant the first
       rotation committed, which is the exact event the second caller raced.
       The window is never restarted by a grace re-issue, so a token cannot be
       kept alive indefinitely by presenting it over and over.
    2. Revoked *by rotation*, not by anything else. ``revoked_at`` is also set
       by logout and by mass revocation, and those must stay dead. Only a
       rotation leaves a replacement row pointing back at this token, so the
       existence of that child is what distinguishes the two.
    3. The user still has at least one live token. After ``_revoke_all_for_user``
       every row is revoked; re-issuing from one of them would undo a
       deliberate kill (a logout-all, or a genuine theft detection that fired
       between the rotation and this call).
    """
    grace = timedelta(seconds=get_settings().refresh_reuse_grace_seconds)
    if token.revoked_at is None or now - token.revoked_at >= grace:
        return False
    rotated_not_logged_out = db.scalar(select(RefreshToken.id).where(RefreshToken.rotated_from_id == token.id).limit(1))
    if rotated_not_logged_out is None:
        return False
    chain_still_live = db.scalar(
        select(RefreshToken.id)
        .where(RefreshToken.user_id == token.user_id, RefreshToken.revoked_at.is_(None))
        .limit(1)
    )
    return chain_still_live is not None


def rotate_refresh_token(db: Session, presented_secret: str) -> AuthTokensOut:
    settings = get_settings()
    invalid = api_error(status.HTTP_401_UNAUTHORIZED, code="invalid_refresh_token", message="Please sign in again.")
    token_hash = hash_refresh_token(presented_secret)
    # with_for_update: two callers racing with the *same* token must not both
    # read revoked_at as NULL and both rotate. Serialising on this one row
    # means the loser re-reads a committed revoked_at and takes one of the two
    # branches below deliberately, instead of the outcome depending on
    # snapshot timing. It also closes the equivalent hole in theft detection,
    # where two racing uses of a stolen token could both slip through.
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update())
    if not token:
        raise invalid
    now = datetime.now(timezone.utc)
    if token.revoked_at is not None:
        if token.expires_at >= now and _is_benign_concurrent_refresh(db, token, now):
            # A racing client, not an attacker. Mint a *fresh* pair parented to
            # the same token: the replacement minted by the first refresh was
            # handed out as a one-time secret and only its SHA-256 hash was
            # kept, so it cannot be handed out a second time even in principle.
            # revoked_at is deliberately left at its original value -- see
            # condition 1 above.
            new_refresh = _issue_refresh_token(db, token.user_id, rotated_from_id=token.id)
            db.commit()
            emit_event("refresh_token_grace_reissue", user_id=token.user_id)
            return AuthTokensOut(
                access_token=create_access_token(token.user_id),
                refresh_token=new_refresh.secret,
                expires_in=settings.access_token_minutes * 60,
                is_new_user=False,
            )
        # Reuse of an already-rotated or already-revoked token: treat as a
        # likely theft and kill every session for this user, not just this
        # token's descendants, so the legitimate holder is forced to
        # re-authenticate and notice something happened.
        _revoke_all_for_user(db, token.user_id)
        db.commit()
        emit_event("refresh_token_reuse_detected", user_id=token.user_id)
        raise invalid
    if token.expires_at < now:
        raise invalid

    token.revoked_at = now
    new_refresh = _issue_refresh_token(db, token.user_id, rotated_from_id=token.id)
    db.commit()
    return AuthTokensOut(
        access_token=create_access_token(token.user_id),
        refresh_token=new_refresh.secret,
        expires_in=settings.access_token_minutes * 60,
        is_new_user=False,
    )


def revoke_refresh_token(db: Session, presented_secret: str) -> None:
    token_hash = hash_refresh_token(presented_secret)
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if token and token.revoked_at is None:
        token.revoked_at = datetime.now(timezone.utc)
        db.commit()


def revoke_all_refresh_tokens(db: Session, user_id: uuid.UUID) -> None:
    _revoke_all_for_user(db, user_id)
    db.commit()


def _revoke_all_for_user(db: Session, user_id: uuid.UUID) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
