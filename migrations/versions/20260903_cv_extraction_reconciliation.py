"""Add lease/attempt tracking to cv_versions for extraction reconciliation.

Mirrors tailored_documents.processing_lease_expires_at: before this, a CV
version whose extraction task never ran (Redis outage between commit and
enqueue) or whose worker crashed mid-extraction had no mechanism to recover
-- it sat in `uploaded` or `extracting` forever, silently blocking tailoring
and email-apply for that user. See reconcile_stale_cv_extractions in
app/cv_tailoring/tasks.py.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260903_cv_extraction_reconciliation"
down_revision = "20260902_email_password_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cv_versions", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.alter_column("cv_versions", "attempt_count", server_default=None)
    op.add_column("cv_versions", sa.Column("processing_lease_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("cv_versions", "processing_lease_expires_at")
    op.drop_column("cv_versions", "attempt_count")
