"""Widen listings.location from VARCHAR(255) to TEXT.

Same rationale as the apply_target widening in this same migration chain: a
real ingestion run against all five DPSA circulars hit
StringDataRightTruncation on location too, this time at 255 chars -- some
posts are advertised across many districts at once, each carrying its own
embedded reference number (one real example ran past 2,000 characters).
Every other source's location is a short place name and is unaffected;
widening costs nothing (TEXT and VARCHAR(n) are identical in Postgres aside
from the length check) and avoids silently dropping districts a candidate
could genuinely apply to.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260913_listing_location_text"
down_revision = "20260913_apply_target_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("listings", "location", type_=sa.Text(), existing_type=sa.String(length=255), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("listings", "location", type_=sa.String(length=255), existing_type=sa.Text(), existing_nullable=True)
