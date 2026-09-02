"""Add CV tailoring resources to the established legacy Phanda schema.

This revision intentionally contains no legacy table creation — those tables
are created by ``20260101_baseline_legacy_schema``, which this revision is
now parented on. (It previously had ``down_revision = None`` and assumed the
legacy schema already existed by some other means; that gap is what the
baseline revision fixes.)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260831_add_cv_tailoring"
down_revision = "20260101_baseline_legacy_schema"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> postgresql.ENUM:
    enum = postgresql.ENUM(*values, name=name, create_type=False)
    enum.create(op.get_bind(), checkfirst=True)
    return enum


def upgrade() -> None:
    cv_status = _enum("cvversionstatus", "uploaded", "extracting", "ready", "failed")
    document_status = _enum("tailoreddocumentstatus", "queued", "processing", "validating", "rendering", "ready", "failed", "cancelled")
    reservation_status = _enum("reservationstatus", "reserved", "consumed", "released", "expired")
    reservation_source = _enum("reservationsource", "free", "rewarded", "premium")
    submission_status = _enum("applicationsubmissionstatus", "not_started", "external_started", "email_queued", "email_sent", "email_failed", "email_unknown")

    # Existing applicationstatus is a legacy type.  PostgreSQL enum labels are
    # additive but cannot be safely removed during downgrade.
    op.execute("ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS 'prepared'")
    op.execute("ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS 'external_started'")

    op.create_table(
        "cv_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", cv_status, nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False, unique=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("extracted_text_key", sa.String(length=1024), nullable=True),
        sa.Column("candidate_facts_json", postgresql.JSONB(), nullable=True),
        sa.Column("failure_code", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "version_number", name="uq_cv_version_number"),
        sa.UniqueConstraint("user_id", "sha256", name="uq_cv_version_hash"),
    )
    op.create_index("ix_cv_versions_user_id", "cv_versions", ["user_id"])

    op.create_table(
        "tailored_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id"), nullable=False),
        sa.Column("cv_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cv_versions.id"), nullable=False),
        sa.Column("status", document_status, nullable=False),
        sa.Column("tailored_cv_key", sa.String(length=1024), nullable=True),
        sa.Column("cover_letter_key", sa.String(length=1024), nullable=True),
        sa.Column("output_format", sa.String(length=20), nullable=False),
        sa.Column("listing_snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("profile_snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("provider_name", sa.String(length=80), nullable=True),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("correction_attempted", sa.Boolean(), nullable=False),
        sa.Column("processing_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "listing_id", "cv_version_id", name="uq_tailored_document_input"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_tailored_document_idempotency"),
    )
    op.create_index("ix_tailored_documents_user_id", "tailored_documents", ["user_id"])
    op.create_index("ix_tailored_documents_listing_id", "tailored_documents", ["listing_id"])
    op.create_index("ix_tailored_documents_cv_version_id", "tailored_documents", ["cv_version_id"])

    op.create_table(
        "tailoring_request_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tailored_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tailored_documents.id"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("source", reservation_source, nullable=False),
        sa.Column("status", reservation_status, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tailored_document_id", name="uq_reservation_document"),
    )
    op.create_index("ix_tailoring_request_reservations_user_id", "tailoring_request_reservations", ["user_id"])

    op.create_table(
        "reward_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("credits_granted", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "external_event_id", name="uq_reward_event_external"),
    )
    op.create_index("ix_reward_events_user_id", "reward_events", ["user_id"])

    op.add_column("profiles", sa.Column("active_cv_version_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_profiles_active_cv_version", "profiles", "cv_versions", ["active_cv_version_id"], ["id"])

    op.add_column("applications", sa.Column("tailored_document_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_applications_tailored_document", "applications", "tailored_documents", ["tailored_document_id"], ["id"])
    op.create_index("ix_applications_tailored_document_id", "applications", ["tailored_document_id"])
    op.add_column("applications", sa.Column("submission_status", submission_status, nullable=False, server_default="not_started"))
    op.alter_column("applications", "submission_status", server_default=None)
    op.add_column("applications", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.create_unique_constraint("uq_application_idempotency", "applications", ["user_id", "idempotency_key"])
    op.add_column("applications", sa.Column("email_provider_message_id", sa.String(length=255), nullable=True))
    op.add_column("applications", sa.Column("email_attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.alter_column("applications", "email_attempt_count", server_default=None)


def downgrade() -> None:
    op.drop_column("applications", "email_attempt_count")
    op.drop_column("applications", "email_provider_message_id")
    op.drop_constraint("uq_application_idempotency", "applications", type_="unique")
    op.drop_column("applications", "idempotency_key")
    op.drop_column("applications", "submission_status")
    op.drop_index("ix_applications_tailored_document_id", table_name="applications")
    op.drop_constraint("fk_applications_tailored_document", "applications", type_="foreignkey")
    op.drop_column("applications", "tailored_document_id")
    op.drop_constraint("fk_profiles_active_cv_version", "profiles", type_="foreignkey")
    op.drop_column("profiles", "active_cv_version_id")
    op.drop_index("ix_reward_events_user_id", table_name="reward_events")
    op.drop_table("reward_events")
    op.drop_index("ix_tailoring_request_reservations_user_id", table_name="tailoring_request_reservations")
    op.drop_table("tailoring_request_reservations")
    op.drop_index("ix_tailored_documents_cv_version_id", table_name="tailored_documents")
    op.drop_index("ix_tailored_documents_listing_id", table_name="tailored_documents")
    op.drop_index("ix_tailored_documents_user_id", table_name="tailored_documents")
    op.drop_table("tailored_documents")
    op.drop_index("ix_cv_versions_user_id", table_name="cv_versions")
    op.drop_table("cv_versions")
    # applicationstatus retains prepared/external_started by design; PostgreSQL
    # does not support safe transactional removal of enum labels.
