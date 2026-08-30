from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.auth.schemas import OtpRequestIn, OtpRequestOut, OtpVerifyIn, TokenOut
from app.auth.sms import send_otp_sms
from app.core.config import get_settings
from app.core.db import get_db
from app.core.models import OtpChallenge, Profile, User
from app.core.security import create_access_token, generate_otp, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/otp/request", response_model=OtpRequestOut)
async def request_otp(payload: OtpRequestIn, db: Session = Depends(get_db)) -> OtpRequestOut:
    settings = get_settings()
    otp = generate_otp()
    challenge = OtpChallenge(
        phone_number=payload.phone_number,
        otp_code=otp,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.otp_ttl_minutes),
    )
    db.add(challenge)
    db.commit()

    await send_otp_sms(payload.phone_number, otp)
    return OtpRequestOut(message="OTP sent", dev_otp=otp if settings.otp_dev_mode else None)


@router.post("/otp/verify", response_model=TokenOut)
def verify_otp(payload: OtpVerifyIn, db: Session = Depends(get_db)) -> TokenOut:
    challenge = db.scalar(
        select(OtpChallenge)
        .where(
            OtpChallenge.phone_number == payload.phone_number,
            OtpChallenge.consumed_at.is_(None),
        )
        .order_by(desc(OtpChallenge.created_at))
    )
    now = datetime.now(timezone.utc)
    if not challenge or challenge.otp_code != payload.otp_code or challenge.expires_at < now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP")

    user = db.scalar(select(User).where(User.phone_number == payload.phone_number))
    if not user:
        user = User(phone_number=payload.phone_number)
        db.add(user)
        db.flush()
        db.add(Profile(user_id=user.id))

    challenge.consumed_at = now
    db.commit()
    return TokenOut(access_token=create_access_token(user.id))


@router.post("/refresh", response_model=TokenOut)
def refresh_token(user: User = Depends(get_current_user)) -> TokenOut:
    return TokenOut(access_token=create_access_token(user.id))
