"""Add listings.category, a source-provided industry/category label.

Backs the recommendation engine's industry-compatibility factor with a real,
source-verified field (Adzuna's `category.label`) instead of guessing
industry from free-text title/description matching.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260904_listing_category"
down_revision = "20260903_cv_extraction_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("category", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "category")
