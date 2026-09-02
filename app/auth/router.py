from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.google import GoogleAuthNotConfigured, verify_google_id_token
from app.auth.schemas import AuthTokensOut, GoogleAuthIn, LoginIn, LogoutIn, RefreshIn, RegisterIn
from app.core.db import get_db
from app.core.errors import api_error
from app.core.models import User
from app.core.rate_limit import check_rate_limit
from app.core.security import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/register", response_model=AuthTokensOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn, request: Request, db: Session = Depends(get_db)) -> AuthTokensOut:
    check_rate_limit(bucket="register:ip", key=_client_ip(request), limit=10, window_seconds=3600)
    user = service.register_with_password(db, email=payload.email, password=payload.password)
    return service.issue_tokens(db, user, is_new_user=True)


@router.post("/login", response_model=AuthTokensOut)
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)) -> AuthTokensOut:
    check_rate_limit(bucket="login:ip", key=_client_ip(request), limit=30, window_seconds=3600)
    check_rate_limit(bucket="login:email", key=payload.email.lower(), limit=8, window_seconds=900)
    user = service.authenticate_with_password(db, email=payload.email, password=payload.password)
    return service.issue_tokens(db, user, is_new_user=False)


@router.post("/google", response_model=AuthTokensOut)
def google_auth(payload: GoogleAuthIn, request: Request, db: Session = Depends(get_db)) -> AuthTokensOut:
    check_rate_limit(bucket="google:ip", key=_client_ip(request), limit=30, window_seconds=3600)
    try:
        identity = verify_google_id_token(payload.id_token)
    except GoogleAuthNotConfigured as exc:
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE, code="google_auth_not_configured", message="Google sign-in is not available right now."
        ) from exc
    user, is_new_user = service.authenticate_or_create_with_google(db, identity)
    return service.issue_tokens(db, user, is_new_user=is_new_user)


@router.post("/token/refresh", response_model=AuthTokensOut)
def refresh(payload: RefreshIn, request: Request, db: Session = Depends(get_db)) -> AuthTokensOut:
    check_rate_limit(bucket="refresh:ip", key=_client_ip(request), limit=60, window_seconds=3600)
    return service.rotate_refresh_token(db, payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: LogoutIn, db: Session = Depends(get_db)) -> Response:
    service.revoke_refresh_token(db, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    service.revoke_all_refresh_tokens(db, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
