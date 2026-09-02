"""Add listings.last_seen_at for scheduled listing expiry.

Backs deactivate_stale_listings: a listing not seen in a source pull for
Settings.listing_stale_after_days is deactivated, on the assumption it was
filled or withdrawn. Existing rows backfill to ingested_at, their best
available proxy for "last confirmed present".
"""
from alembic import op
import sqlalchemy as sa

revision = "20260905_listing_last_seen"
down_revision = "20260904_listing_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE listings SET last_seen_at = ingested_at WHERE last_seen_at IS NULL")
    op.alter_column("listings", "last_seen_at", existing_type=sa.DateTime(timezone=True), nullable=False)


def downgrade() -> None:
    op.drop_column("listings", "last_seen_at")
