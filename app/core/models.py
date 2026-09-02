import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobType(str, enum.Enum):
    full_time = "full_time"
    part_time = "part_time"
    internship = "internship"
    learnership = "learnership"
    any = "any"


class ExperienceLevel(str, enum.Enum):
    none = "none"
    some = "some"
    experienced = "experienced"


class ListingType(str, enum.Enum):
    job = "job"
    internship = "internship"
    learnership = "learnership"
    apprenticeship = "apprenticeship"
    bursary = "bursary"


class ApplyMethod(str, enum.Enum):
    ats_link = "ats_link"
    email = "email"


class ApplicationStatus(str, enum.Enum):
    prepared = "prepared"
    external_started = "external_started"
    applied = "applied"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"
    withdrawn = "withdrawn"


class AppliedVia(str, enum.Enum):
    phanda_email = "phanda_email"
    external_link = "external_link"


class CvVersionStatus(str, enum.Enum):
    uploaded = "uploaded"
    extracting = "extracting"
    ready = "ready"
    failed = "failed"


class TailoredDocumentStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    validating = "validating"
    rendering = "rendering"
    ready = "ready"
    failed = "failed"
    cancelled = "cancelled"


class ReservationStatus(str, enum.Enum):
    reserved = "reserved"
    consumed = "consumed"
    released = "released"
    expired = "expired"


class ReservationSource(str, enum.Enum):
    free = "free"
    rewarded = "rewarded"
    premium = "premium"


class ApplicationSubmissionStatus(str, enum.Enum):
    not_started = "not_started"
    external_started = "external_started"
    email_queued = "email_queued"
    email_sent = "email_sent"
    email_failed = "email_failed"
    email_unknown = "email_unknown"


class AuthProvider(str, enum.Enum):
    google = "google"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    """Null for a user who has only ever authenticated with an OAuth provider."""
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped["Profile"] = relationship(back_populates="user", uselist=False)


class UserAuthIdentity(Base):
    """A linked external identity (currently Google) for a user.

    Password auth needs no row here — it lives directly on ``users`` since
    every user has at most one password. This table exists so a user who
    registered with email/password can later link Google (or vice versa)
    without Phanda ever creating two separate accounts for the same person:
    linking happens by matching the OAuth provider's verified email against
    an existing ``users.email`` before falling back to creating a new user.
    """

    __tablename__ = "user_auth_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_subject", name="uq_auth_identity_provider_subject"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    provider: Mapped[AuthProvider] = mapped_column(Enum(AuthProvider, native_enum=False, length=30))
    provider_subject: Mapped[str] = mapped_column(String(255))
    """The provider's stable subject identifier (Google's ``sub`` claim) —
    never the email address, which a provider account can change."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RefreshToken(Base):
    """One issued refresh token. Only its hash is stored, so a stolen database
    dump cannot be replayed as a session the way a stored plaintext token could.

    Rotation: each ``/auth/token/refresh`` call revokes the presented token and
    issues a new row with ``rotated_from_id`` pointing at it. Presenting an
    already-rotated (or already-revoked) token is treated as reuse — the whole
    chain descending from it is revoked, since that pattern means a token was
    stolen and both the attacker and the legitimate holder are now racing to
    use it.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_from_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("refresh_tokens.id"), nullable=True)
    device_label: Mapped[str | None] = mapped_column(String(120), nullable=True)


class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    job_type: Mapped[JobType] = mapped_column(Enum(JobType), default=JobType.any)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    open_to_remote: Mapped[bool] = mapped_column(Boolean, default=False)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    industries: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    education_level: Mapped[str | None] = mapped_column(String(120), nullable=True)
    experience_level: Mapped[ExperienceLevel] = mapped_column(Enum(ExperienceLevel), default=ExperienceLevel.none)
    desired_salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    desired_salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cv_file_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    active_cv_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cv_versions.id"), nullable=True
    )
    profile_completeness: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped[User] = relationship(back_populates="profile")
    active_cv_version: Mapped["CvVersion | None"] = relationship(foreign_keys=[active_cv_version_id])


class CvVersion(Base):
    __tablename__ = "cv_versions"
    __table_args__ = (
        UniqueConstraint("user_id", "version_number", name="uq_cv_version_number"),
        UniqueConstraint("user_id", "sha256", name="uq_cv_version_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[CvVersionStatus] = mapped_column(Enum(CvVersionStatus), default=CvVersionStatus.uploaded)
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    byte_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_text_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    candidate_facts_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    processing_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """Set while a Celery worker is (or should be) extracting this version.
    A scheduled reconciliation task requeues or fails versions whose lease
    has expired -- mirroring TailoredDocument's lease, which exists for the
    same reason: a worker crash between "committed the enqueue" and
    "finished the task" must not leave the row stuck forever."""


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (UniqueConstraint("source", "source_listing_id", name="uq_listing_source_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(80), index=True)
    source_listing_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    listing_type: Mapped[ListingType] = mapped_column(Enum(ListingType), default=ListingType.job)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    """Source-provided industry/category label (e.g. Adzuna's category.label)
    -- used as the recommendation engine's industry-compatibility signal.
    Left null for sources that don't provide one rather than guessed from
    free text."""
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(Text)
    required_skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    apply_method: Mapped[ApplyMethod] = mapped_column(Enum(ApplyMethod))
    apply_target: Mapped[str] = mapped_column(String(1024))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    """Refreshed every time this listing appears in a source pull. A
    scheduled task deactivates any listing not seen for
    Settings.listing_stale_after_days -- it disappeared from the source,
    which most often means it was filled or withdrawn."""
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_application_idempotency"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listings.id"), index=True)
    status: Mapped[ApplicationStatus] = mapped_column(Enum(ApplicationStatus), default=ApplicationStatus.applied)
    tailored_cv_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    tailored_cover_letter_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    tailored_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tailored_documents.id"), nullable=True, index=True
    )
    submission_status: Mapped[ApplicationSubmissionStatus] = mapped_column(
        Enum(ApplicationSubmissionStatus), default=ApplicationSubmissionStatus.not_started
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    applied_via: Mapped[AppliedVia] = mapped_column(Enum(AppliedVia))
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    listing: Mapped[Listing] = relationship()


class TailoredDocument(Base):
    __tablename__ = "tailored_documents"
    __table_args__ = (
        UniqueConstraint("user_id", "listing_id", "cv_version_id", name="uq_tailored_document_input"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_tailored_document_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listings.id"), index=True)
    cv_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cv_versions.id"), index=True)
    status: Mapped[TailoredDocumentStatus] = mapped_column(
        Enum(TailoredDocumentStatus), default=TailoredDocumentStatus.queued
    )
    tailored_cv_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    cover_letter_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    output_format: Mapped[str] = mapped_column(String(20), default="pdf")
    listing_snapshot_json: Mapped[dict] = mapped_column(JSONB)
    profile_snapshot_json: Mapped[dict] = mapped_column(JSONB)
    provider_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(40), default="v1")
    idempotency_key: Mapped[str] = mapped_column(String(255))
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    correction_attempted: Mapped[bool] = mapped_column(Boolean, default=False)
    processing_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TailoringRequestReservation(Base):
    __tablename__ = "tailoring_request_reservations"
    __table_args__ = (UniqueConstraint("tailored_document_id", name="uq_reservation_document"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    tailored_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tailored_documents.id"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date)
    source: Mapped[ReservationSource] = mapped_column(Enum(ReservationSource))
    status: Mapped[ReservationStatus] = mapped_column(Enum(ReservationStatus), default=ReservationStatus.reserved)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RewardEvent(Base):
    __tablename__ = "reward_events"
    __table_args__ = (UniqueConstraint("provider", "external_event_id", name="uq_reward_event_external"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(80))
    external_event_id: Mapped[str] = mapped_column(String(255))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    credits_granted: Mapped[int] = mapped_column(Integer, default=1)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SavedOpportunity(Base):
    __tablename__ = "saved_opportunities"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listings.id"), primary_key=True)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    listing: Mapped[Listing] = relationship()


class FeatureUsage(Base):
    __tablename__ = "feature_usage"
    __table_args__ = (UniqueConstraint("user_id", "feature_key", "period_start", name="uq_feature_usage_period"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    feature_key: Mapped[str] = mapped_column(String(80), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    free_uses_count: Mapped[int] = mapped_column(Integer, default=0)
    ad_reward_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    ad_reward_used_today: Mapped[bool] = mapped_column(Boolean, default=False)


class Entitlement(Base):
    __tablename__ = "entitlements"
    __table_args__ = (UniqueConstraint("user_id", "entitlement_key", name="uq_user_entitlement"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    entitlement_key: Mapped[str] = mapped_column(String(120), default="phanda_premium")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    revenuecat_customer_id: Mapped[str] = mapped_column(String(255), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Wallet(Base):
    __tablename__ = "wallet"
    __table_args__ = (UniqueConstraint("user_id", "currency_key", name="uq_user_currency"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    currency_key: Mapped[str] = mapped_column(String(120), default="boost_tokens")
    balance: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
