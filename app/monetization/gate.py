import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.models import Entitlement, FeatureUsage, Wallet

PREMIUM_ENTITLEMENT = "phanda_premium"
BOOST_CURRENCY = "boost_tokens"


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str
    should_offer_ad: bool = False
    should_show_paywall: bool = False


def monthly_period_start(today: date | None = None) -> date:
    current = today or date.today()
    return current.replace(day=1)


def check_access(db: Session, user_id: uuid.UUID, feature_key: str) -> AccessDecision:
    settings = get_settings()
    entitlement = db.scalar(
        select(Entitlement).where(
            Entitlement.user_id == user_id,
            Entitlement.entitlement_key == PREMIUM_ENTITLEMENT,
            Entitlement.is_active.is_(True),
        )
    )
    if entitlement:
        return AccessDecision(allowed=True, reason="premium")

    today = date.today()
    usage = _get_or_create_usage(db, user_id, feature_key, monthly_period_start(today))
    free_cap = _free_cap_for_feature(feature_key, settings)
    if usage.free_uses_count < free_cap:
        usage.free_uses_count += 1
        db.commit()
        return AccessDecision(allowed=True, reason="free_quota")

    wallet = db.scalar(select(Wallet).where(Wallet.user_id == user_id, Wallet.currency_key == BOOST_CURRENCY))
    has_daily_ad_slot = usage.ad_reward_date != today
    if wallet and wallet.balance > 0 and has_daily_ad_slot:
        wallet.balance -= 1
        usage.ad_reward_date = today
        usage.ad_reward_used_today = True
        db.commit()
        return AccessDecision(allowed=True, reason="boost_token")

    if has_daily_ad_slot:
        return AccessDecision(allowed=False, reason="watch_ad_available", should_offer_ad=True)
    return AccessDecision(allowed=False, reason="paywall_required", should_show_paywall=True)


def _get_or_create_usage(db: Session, user_id: uuid.UUID, feature_key: str, period_start: date) -> FeatureUsage:
    usage = db.scalar(
        select(FeatureUsage).where(
            FeatureUsage.user_id == user_id,
            FeatureUsage.feature_key == feature_key,
            FeatureUsage.period_start == period_start,
        )
    )
    if usage:
        return usage
    usage = FeatureUsage(user_id=user_id, feature_key=feature_key, period_start=period_start)
    db.add(usage)
    db.flush()
    return usage


def _free_cap_for_feature(feature_key: str, settings) -> int:
    if feature_key == "cv_tailor":
        return settings.monthly_free_cv_tailor
    if feature_key == "skill_gap_roadmap":
        return settings.monthly_free_skill_gap_roadmap
    return 0

