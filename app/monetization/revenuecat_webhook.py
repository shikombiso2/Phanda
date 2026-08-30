import hashlib
import hmac
import time
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.models import Entitlement, Wallet
from app.monetization.gate import BOOST_CURRENCY, PREMIUM_ENTITLEMENT

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

PURCHASE_ACTIVE_EVENTS = {"INITIAL_PURCHASE", "RENEWAL", "UNCANCELLATION", "PRODUCT_CHANGE"}
PURCHASE_INACTIVE_EVENTS = {"CANCELLATION", "EXPIRATION", "BILLING_ISSUE"}
VIRTUAL_CURRENCY_EVENTS = {"VIRTUAL_CURRENCY_TRANSACTION", "VIRTUAL_CURRENCY_BALANCE_CHANGED"}


@router.post("/revenuecat")
async def revenuecat_webhook(
    request: Request,
    db: Session = Depends(get_db),
    signature: str | None = Header(default=None, alias="X-RevenueCat-Webhook-Signature"),
) -> dict[str, str]:
    raw_body = await request.body()
    settings = get_settings()
    if settings.revenuecat_webhook_secret and not _verify_signature(raw_body, signature, settings.revenuecat_webhook_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid RevenueCat signature")

    payload = await request.json()
    event = payload.get("event", {})
    event_type = event.get("type")
    app_user_id = event.get("app_user_id") or event.get("aliases", [None])[0]
    user_id = _parse_user_id(app_user_id)
    if not user_id:
        return {"status": "ignored"}

    if event_type in PURCHASE_ACTIVE_EVENTS | PURCHASE_INACTIVE_EVENTS:
        _upsert_entitlement(
            db,
            user_id=user_id,
            revenuecat_customer_id=event.get("app_user_id") or str(user_id),
            is_active=event_type in PURCHASE_ACTIVE_EVENTS,
        )
    elif event_type in VIRTUAL_CURRENCY_EVENTS or event.get("currency") or event.get("currency_key"):
        _upsert_wallet(db, user_id=user_id, balance=_extract_balance(event))

    db.commit()
    return {"status": "ok"}


def _verify_signature(payload: bytes, header: str | None, secret: str, tolerance_seconds: int = 300) -> bool:
    if not header:
        return False
    try:
        parts = dict(part.split("=", 1) for part in header.split(","))
        timestamp = parts["t"]
        expected = parts["v1"]
        signed_payload = f"{timestamp}.".encode() + payload
        computed = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed, expected) and abs(time.time() - int(timestamp)) <= tolerance_seconds
    except Exception:
        return False


def _parse_user_id(value: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _upsert_entitlement(db: Session, user_id: uuid.UUID, revenuecat_customer_id: str, is_active: bool) -> None:
    entitlement = db.scalar(
        select(Entitlement).where(Entitlement.user_id == user_id, Entitlement.entitlement_key == PREMIUM_ENTITLEMENT)
    )
    if not entitlement:
        entitlement = Entitlement(
            user_id=user_id,
            entitlement_key=PREMIUM_ENTITLEMENT,
            revenuecat_customer_id=revenuecat_customer_id,
        )
        db.add(entitlement)
    entitlement.is_active = is_active
    entitlement.revenuecat_customer_id = revenuecat_customer_id


def _upsert_wallet(db: Session, user_id: uuid.UUID, balance: int) -> None:
    wallet = db.scalar(select(Wallet).where(Wallet.user_id == user_id, Wallet.currency_key == BOOST_CURRENCY))
    if not wallet:
        wallet = Wallet(user_id=user_id, currency_key=BOOST_CURRENCY)
        db.add(wallet)
    wallet.balance = balance


def _extract_balance(event: dict) -> int:
    for key in ("balance", "new_balance", "virtual_currency_balance"):
        if event.get(key) is not None:
            return int(event[key])
    if event.get("amount") is not None:
        return max(0, int(event["amount"]))
    return 0

