import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.models import (
    CvVersion,
    Entitlement,
    FeatureUsage,
    Listing,
    Profile,
    ReservationSource,
    ReservationStatus,
    TailoredDocument,
    TailoredDocumentStatus,
    TailoringRequestReservation,
    Wallet,
)

PREMIUM_ENTITLEMENT = "phanda_premium"
BOOST_CURRENCY = "boost_tokens"
TAILORING_CURRENCY = "tailoring_requests"


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str
    should_offer_ad: bool = False
    should_show_paywall: bool = False


@dataclass(frozen=True)
class TailoringAllowance:
    included_remaining: int
    rewarded_credits_available: int
    premium_active: bool
    premium_remaining: int | None
    should_offer_ad: bool
    should_show_paywall: bool


@dataclass(frozen=True)
class ReservationResult:
    document: TailoredDocument
    created: bool


def monthly_period_start(today: date | None = None) -> date:
    current = today or date.today()
    return current.replace(day=1)


def check_access(db: Session, user_id: uuid.UUID, feature_key: str) -> AccessDecision:
    """Compatibility gate for non-tailoring features.

    Tailoring consumes capacity only through ``reserve_tailoring_request``.
    """
    if feature_key == "cv_tailor":
        allowance = get_tailoring_allowance(db, user_id)
        return AccessDecision(
            allowed=allowance.included_remaining > 0
            or allowance.rewarded_credits_available > 0
            or (allowance.premium_remaining or 0) > 0,
            reason="tailoring_reservation_required",
            should_offer_ad=allowance.should_offer_ad,
            should_show_paywall=allowance.should_show_paywall,
        )
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


def get_tailoring_allowance(db: Session, user_id: uuid.UUID) -> TailoringAllowance:
    settings = get_settings()
    period_start = monthly_period_start()
    premium = _has_premium(db, user_id)
    usage = db.scalar(
        select(FeatureUsage).where(
            FeatureUsage.user_id == user_id,
            FeatureUsage.feature_key == "cv_tailor",
            FeatureUsage.period_start == period_start,
        )
    )
    consumed_free = usage.free_uses_count if usage else 0
    reserved_free = _reservation_count(db, user_id, period_start, ReservationSource.free, statuses=[ReservationStatus.reserved])
    included_remaining = max(0, settings.monthly_free_cv_tailor - consumed_free - reserved_free)
    wallet = db.scalar(select(Wallet).where(Wallet.user_id == user_id, Wallet.currency_key == TAILORING_CURRENCY))
    rewarded = wallet.balance if wallet else 0
    premium_remaining = None
    if premium:
        premium_remaining = max(
            0,
            settings.premium_monthly_cv_tailor - _reservation_count(db, user_id, period_start, ReservationSource.premium),
        )
    available = included_remaining > 0 or rewarded > 0 or (premium_remaining or 0) > 0
    return TailoringAllowance(
        included_remaining=included_remaining,
        rewarded_credits_available=rewarded,
        premium_active=premium,
        premium_remaining=premium_remaining,
        should_offer_ad=not available,
        should_show_paywall=not available,
    )


def reserve_tailoring_request(
    db: Session,
    *,
    user_id: uuid.UUID,
    listing: Listing,
    profile: Profile,
    cv_version: CvVersion,
    idempotency_key: str,
) -> ReservationResult:
    """Atomically create a queued document and reserve one Phanda request."""
    settings = get_settings()
    period_start = monthly_period_start()
    usage = _get_or_create_locked_usage(db, user_id, period_start)
    by_idempotency = db.scalar(
        select(TailoredDocument)
        .where(TailoredDocument.user_id == user_id, TailoredDocument.idempotency_key == idempotency_key)
        .with_for_update()
    )
    if by_idempotency:
        return ReservationResult(document=by_idempotency, created=False)
    existing = db.scalar(
        select(TailoredDocument)
        .where(
            TailoredDocument.user_id == user_id,
            TailoredDocument.listing_id == listing.id,
            TailoredDocument.cv_version_id == cv_version.id,
        )
        .with_for_update()
    )
    if existing and existing.status not in {TailoredDocumentStatus.failed, TailoredDocumentStatus.cancelled}:
        return ReservationResult(document=existing, created=False)
    retry_document = None
    if existing:
        _release_existing_reservation(db, existing.id)
        retry_document = existing

    source = _choose_reservation_source(db, user_id, period_start, usage, settings)
    if not source:
        raise PermissionError("No tailoring requests are available")

    snapshot = {
        "title": listing.title,
        "company": listing.company,
        "location": listing.location,
        "description": listing.description,
        "required_skills": listing.required_skills,
    }
    profile_snapshot = {
        "location": profile.location,
        "skills": profile.skills,
        "industries": profile.industries,
        "education_level": profile.education_level,
        "experience_level": profile.experience_level.value if profile.experience_level else None,
    }
    fingerprint = _fingerprint(cv_version.sha256, snapshot, profile_snapshot)
    if retry_document:
        document = retry_document
        document.status = TailoredDocumentStatus.queued
        document.listing_snapshot_json = snapshot
        document.profile_snapshot_json = profile_snapshot
        document.input_fingerprint = fingerprint
        document.idempotency_key = idempotency_key
        document.provider_name = settings.ai_provider
        document.model_name = settings.ai_model
        document.tailored_cv_key = document.cover_letter_key = None
        document.failure_code = None
        document.attempt_count = 0
        document.correction_attempted = False
        document.processing_lease_expires_at = document.ready_at = None
    else:
        document = TailoredDocument(
            user_id=user_id, listing_id=listing.id, cv_version_id=cv_version.id,
            listing_snapshot_json=snapshot, profile_snapshot_json=profile_snapshot,
            input_fingerprint=fingerprint, idempotency_key=idempotency_key,
            provider_name=settings.ai_provider, model_name=settings.ai_model,
        )
        db.add(document)
        db.flush()
    if source == ReservationSource.rewarded:
        wallet = db.scalar(
            select(Wallet)
            .where(Wallet.user_id == user_id, Wallet.currency_key == TAILORING_CURRENCY)
            .with_for_update()
        )
        if not wallet or wallet.balance < 1:
            raise PermissionError("No rewarded tailoring requests are available")
        wallet.balance -= 1
    reservation = db.scalar(select(TailoringRequestReservation).where(TailoringRequestReservation.tailored_document_id == document.id).with_for_update())
    if reservation:
        reservation.period_start, reservation.source, reservation.status = period_start, source, ReservationStatus.reserved
        reservation.expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.tailoring_reservation_minutes)
        reservation.finalized_at = None
    else:
        db.add(TailoringRequestReservation(
            user_id=user_id, tailored_document_id=document.id, period_start=period_start, source=source,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.tailoring_reservation_minutes),
        ))
    db.commit()
    db.refresh(document)
    return ReservationResult(document=document, created=True)


def consume_reservation(db: Session, document: TailoredDocument) -> None:
    reservation = db.scalar(
        select(TailoringRequestReservation)
        .where(TailoringRequestReservation.tailored_document_id == document.id)
        .with_for_update()
    )
    if not reservation or reservation.status != ReservationStatus.reserved:
        return
    reservation.status = ReservationStatus.consumed
    reservation.finalized_at = datetime.now(timezone.utc)
    if reservation.source == ReservationSource.free:
        usage = _get_or_create_locked_usage(db, document.user_id, reservation.period_start)
        usage.free_uses_count += 1


def release_reservation(db: Session, document: TailoredDocument) -> None:
    reservation = db.scalar(
        select(TailoringRequestReservation)
        .where(TailoringRequestReservation.tailored_document_id == document.id)
        .with_for_update()
    )
    if not reservation or reservation.status != ReservationStatus.reserved:
        return
    if reservation.source == ReservationSource.rewarded:
        wallet = db.scalar(
            select(Wallet)
            .where(Wallet.user_id == document.user_id, Wallet.currency_key == TAILORING_CURRENCY)
            .with_for_update()
        )
        if not wallet:
            wallet = Wallet(user_id=document.user_id, currency_key=TAILORING_CURRENCY)
            db.add(wallet)
        wallet.balance += 1
    reservation.status = ReservationStatus.released
    reservation.finalized_at = datetime.now(timezone.utc)


def _get_or_create_locked_usage(db: Session, user_id: uuid.UUID, period_start: date) -> FeatureUsage:
    db.execute(
        pg_insert(FeatureUsage)
        .values(user_id=user_id, feature_key="cv_tailor", period_start=period_start)
        .on_conflict_do_nothing(index_elements=["user_id", "feature_key", "period_start"])
    )
    usage = db.scalar(
        select(FeatureUsage)
        .where(
            FeatureUsage.user_id == user_id,
            FeatureUsage.feature_key == "cv_tailor",
            FeatureUsage.period_start == period_start,
        )
        .with_for_update()
    )
    if not usage:
        raise RuntimeError("Unable to lock tailoring usage")
    return usage


def _choose_reservation_source(db: Session, user_id: uuid.UUID, period_start: date, usage: FeatureUsage, settings) -> ReservationSource | None:
    reserved_free = _reservation_count(db, user_id, period_start, ReservationSource.free, statuses=[ReservationStatus.reserved])
    if usage.free_uses_count + reserved_free < settings.monthly_free_cv_tailor:
        return ReservationSource.free
    wallet = db.scalar(
        select(Wallet).where(Wallet.user_id == user_id, Wallet.currency_key == TAILORING_CURRENCY).with_for_update()
    )
    if wallet and wallet.balance > 0:
        return ReservationSource.rewarded
    if _has_premium(db, user_id) and _reservation_count(db, user_id, period_start, ReservationSource.premium) < settings.premium_monthly_cv_tailor:
        return ReservationSource.premium
    return None


def _reservation_count(
    db: Session, user_id: uuid.UUID, period_start: date, source: ReservationSource,
    statuses: list[ReservationStatus] | None = None,
) -> int:
    return db.scalar(
        select(func.count(TailoringRequestReservation.id)).where(
            TailoringRequestReservation.user_id == user_id,
            TailoringRequestReservation.period_start == period_start,
            TailoringRequestReservation.source == source,
            TailoringRequestReservation.status.in_(statuses or [ReservationStatus.reserved, ReservationStatus.consumed]),
        )
    ) or 0


def _has_premium(db: Session, user_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(
            select(Entitlement).where(
                Entitlement.user_id == user_id,
                Entitlement.entitlement_key == PREMIUM_ENTITLEMENT,
                Entitlement.is_active.is_(True),
            )
        )
    )


def _release_existing_reservation(db: Session, document_id: uuid.UUID) -> None:
    reservation = db.scalar(
        select(TailoringRequestReservation)
        .where(TailoringRequestReservation.tailored_document_id == document_id)
        .with_for_update()
    )
    if reservation and reservation.status == ReservationStatus.reserved:
        if reservation.source == ReservationSource.rewarded:
            wallet = db.scalar(
                select(Wallet)
                .where(Wallet.user_id == reservation.user_id, Wallet.currency_key == TAILORING_CURRENCY)
                .with_for_update()
            )
            if not wallet:
                wallet = Wallet(user_id=reservation.user_id, currency_key=TAILORING_CURRENCY)
                db.add(wallet)
            wallet.balance += 1
        reservation.status = ReservationStatus.released
        reservation.finalized_at = datetime.now(timezone.utc)


def _fingerprint(cv_hash: str, listing: dict, profile: dict) -> str:
    import hashlib
    import json

    return hashlib.sha256(f"{cv_hash}:{json.dumps(listing, sort_keys=True)}:{json.dumps(profile, sort_keys=True)}".encode()).hexdigest()
