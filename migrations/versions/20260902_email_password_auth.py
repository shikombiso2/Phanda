"""Replace phone + SMS OTP authentication with email/password + Google.

Product decision: SMS is too expensive at Phanda's expected user volume.
Email becomes the primary unique identity. Password auth uses Argon2id
hashing (see ``app/core/security.py``); Google Sign-In is verified
server-side (see ``app/auth/google.py``) and linked via a new
``user_auth_identities`` table so the same person never ends up with two
accounts regardless of which method they use.

The previous single long-lived JWT (used as both access and refresh
credential) is replaced by a short-lived access JWT plus a revocable,
rotating refresh token, hence ``refresh_tokens``.

This project's own status notes recorded that the live database was never
migrated past the original nine legacy tables — i.e. it has held no
CV-tailoring activity and, as far as this codebase's history shows, no real
(non-seed) users. This migration still backfills rather than deletes any row
that would otherwise violate the new NOT NULL email constraint, on the
chance that assumption is ever wrong for a given environment.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260902_email_password_auth"
down_revision = "20260831_add_cv_tailoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_otp_challenges_phone_number", table_name="otp_challenges")
    op.drop_table("otp_challenges")

    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))

    # Backfill before enforcing NOT NULL so no existing row is silently
    # dropped by this migration. A real user backfilled this way cannot sign
    # in until they use "forgot email"-style support recovery, but their
    # profile, CV versions and applications are preserved intact.
    op.execute("UPDATE users SET email = 'legacy-' || id || '@phanda.invalid' WHERE email IS NULL")
    op.alter_column("users", "email", existing_type=sa.String(length=255), nullable=False)
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    op.drop_index("ix_users_phone_number", table_name="users")
    op.drop_column("users", "phone_number")

    op.create_table(
        "user_auth_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_subject", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "provider_subject", name="uq_auth_identity_provider_subject"),
    )
    op.create_index("ix_user_auth_identities_user_id", "user_auth_identities", ["user_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_from_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("refresh_tokens.id"), nullable=True),
        sa.Column("device_label", sa.String(length=120), nullable=True),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])


def downgrade() -> None:
    """Best-effort structural downgrade.

    Phone numbers are not recoverable — they were dropped, not archived, on
    the way up. A downgraded database gets back the phone_number column
    (nullable, empty) and an empty otp_challenges table, matching this
    project's existing precedent for irreversible changes (see the
    applicationstatus enum note in 20260831_add_cv_tailoring): the shape
    is restored, the data is not.
    """
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_user_auth_identities_user_id", table_name="user_auth_identities")
    op.drop_table("user_auth_identities")

    op.add_column("users", sa.Column("phone_number", sa.String(length=32), nullable=True))
    op.create_index("ix_users_phone_number", "users", ["phone_number"])
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.alter_column("users", "email", existing_type=sa.String(length=255), nullable=True)
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "password_hash")

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
