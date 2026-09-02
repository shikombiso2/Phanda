"""Baseline: the nine tables that predate Alembic in this project.

Before this revision, the only thing that could create these tables was
``Base.metadata.create_all()`` in ``scripts/seed_dev.py`` — there was no
migration for them at all, so ``alembic upgrade head`` failed on an empty
database (the very first table the tailoring revision touches has a foreign
key into a ``users`` table that revision never creates). This revision
reconstructs that pre-Alembic schema exactly as ``20260831_add_cv_tailoring``
already assumed it to be, so that migration can be re-parented onto this one
instead of ``down_revision = None``.

Nothing here is new schema — it is the historical starting point, written
down for the first time.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260101_baseline_legacy_schema"
down_revision = None
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> postgresql.ENUM:
    enum = postgresql.ENUM(*values, name=name, create_type=False)
    enum.create(op.get_bind(), checkfirst=True)
    return enum


def upgrade() -> None:
    job_type = _enum("jobtype", "full_time", "part_time", "internship", "learnership", "any")
    experience_level = _enum("experiencelevel", "none", "some", "experienced")
    listing_type = _enum("listingtype", "job", "internship", "learnership", "apprenticeship", "bursary")
    apply_method = _enum("applymethod", "ats_link", "email")
    # 'prepared' and 'external_started' are added later by 20260831_add_cv_tailoring.
    application_status = _enum("applicationstatus", "applied", "interview", "offer", "rejected", "withdrawn")
    applied_via = _enum("appliedvia", "phanda_email", "external_link")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_phone_number", "users", ["phone_number"])

    op.create_table(
        "otp_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=False),
        sa.Column("otp_code", sa.String(length=12), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_otp_challenges_phone_number", "otp_challenges", ["phone_number"])

    op.create_table(
        "profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True, nullable=False),
        sa.Column("job_type", job_type, nullable=False),
        sa.Column("location", sa.String(length=120), nullable=True),
        sa.Column("open_to_remote", sa.Boolean(), nullable=False),
        sa.Column("skills", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("industries", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("education_level", sa.String(length=120), nullable=True),
        sa.Column("experience_level", experience_level, nullable=False),
        sa.Column("desired_salary_min", sa.Integer(), nullable=True),
        sa.Column("desired_salary_max", sa.Integer(), nullable=True),
        sa.Column("cv_file_url", sa.String(length=1024), nullable=True),
        sa.Column("profile_completeness", sa.Integer(), nullable=False),
    )

    op.create_table(
        "listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_listing_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("listing_type", listing_type, nullable=False),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("required_skills", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("apply_method", apply_method, nullable=False),
        sa.Column("apply_target", sa.String(length=1024), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("source", "source_listing_id", name="uq_listing_source_id"),
    )
    op.create_index("ix_listings_source", "listings", ["source"])

    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id"), nullable=False),
        sa.Column("status", application_status, nullable=False),
        sa.Column("tailored_cv_url", sa.String(length=1024), nullable=True),
        sa.Column("tailored_cover_letter_url", sa.String(length=1024), nullable=True),
        sa.Column("applied_via", applied_via, nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_applications_user_id", "applications", ["user_id"])
    op.create_index("ix_applications_listing_id", "applications", ["listing_id"])

    op.create_table(
        "saved_opportunities",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True, nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id"), primary_key=True, nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "feature_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("feature_key", sa.String(length=80), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("free_uses_count", sa.Integer(), nullable=False),
        sa.Column("ad_reward_date", sa.Date(), nullable=True),
        sa.Column("ad_reward_used_today", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("user_id", "feature_key", "period_start", name="uq_feature_usage_period"),
    )
    op.create_index("ix_feature_usage_user_id", "feature_usage", ["user_id"])
    op.create_index("ix_feature_usage_feature_key", "feature_usage", ["feature_key"])

    op.create_table(
        "entitlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("entitlement_key", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("revenuecat_customer_id", sa.String(length=255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "entitlement_key", name="uq_user_entitlement"),
    )
    op.create_index("ix_entitlements_user_id", "entitlements", ["user_id"])
    op.create_index("ix_entitlements_revenuecat_customer_id", "entitlements", ["revenuecat_customer_id"])

    op.create_table(
        "wallet",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("currency_key", sa.String(length=120), nullable=False),
        sa.Column("balance", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "currency_key", name="uq_user_currency"),
    )
    op.create_index("ix_wallet_user_id", "wallet", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_wallet_user_id", table_name="wallet")
    op.drop_table("wallet")
    op.drop_index("ix_entitlements_revenuecat_customer_id", table_name="entitlements")
    op.drop_index("ix_entitlements_user_id", table_name="entitlements")
    op.drop_table("entitlements")
    op.drop_index("ix_feature_usage_feature_key", table_name="feature_usage")
    op.drop_index("ix_feature_usage_user_id", table_name="feature_usage")
    op.drop_table("feature_usage")
    op.drop_table("saved_opportunities")
    op.drop_index("ix_applications_listing_id", table_name="applications")
    op.drop_index("ix_applications_user_id", table_name="applications")
    op.drop_table("applications")
    op.drop_index("ix_listings_source", table_name="listings")
    op.drop_table("listings")
    op.drop_table("profiles")
    op.drop_index("ix_otp_challenges_phone_number", table_name="otp_challenges")
    op.drop_table("otp_challenges")
    op.drop_index("ix_users_phone_number", table_name="users")
    op.drop_table("users")
    for enum_name in ("appliedvia", "applicationstatus", "applymethod", "listingtype", "experiencelevel", "jobtype"):
        postgresql.ENUM(name=enum_name).drop(op.get_bind(), checkfirst=True)
