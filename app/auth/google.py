"""Server-side verification of Google Sign-In ID tokens.

The Android client obtains a Google ID token through Google's own SDK and
sends only that token here. This module is the trust boundary: the backend
never accepts a client-supplied email as someone's identity — it always
re-derives the verified email and the stable subject (`sub`) from a token
whose signature, issuer, audience and expiry it checked itself against
Google's own public keys.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.core.config import get_settings

_google_request = google_requests.Request()


class GoogleAuthNotConfigured(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedGoogleIdentity:
    subject: str
    email: str
    email_verified: bool


def verify_google_id_token(token: str) -> VerifiedGoogleIdentity:
    settings = get_settings()
    allowed_audiences = settings.google_client_id_list()
    if not allowed_audiences:
        raise GoogleAuthNotConfigured("GOOGLE_OAUTH_CLIENT_IDS is not configured")

    try:
        # audience=None here means "skip the library's built-in single-audience
        # check" — signature, issuer and expiry are still fully verified. The
        # audience is then checked below against the *list* of accepted
        # client IDs, since verify_oauth2_token only supports checking one.
        claims = google_id_token.verify_oauth2_token(token, _google_request, audience=None)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google credential") from exc

    if claims.get("aud") not in allowed_audiences:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google credential")

    subject = claims.get("sub")
    email = claims.get("email")
    if not subject or not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google credential is missing required claims")

    return VerifiedGoogleIdentity(subject=subject, email=email, email_verified=bool(claims.get("email_verified")))
