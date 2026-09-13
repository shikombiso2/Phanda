"""Add listings.salary_period, salary_currency and expires_at.

salary_min/salary_max previously carried no units at all, which was safe
only while every listing came from one source in one country: Adzuna ZA,
whose figures are annual ZAR. A second source (Himalayas) returns hourly
USD alongside annual USD and annual CAD, so an unqualified integer is no
longer interpretable -- 22 and 150000 would render identically as "salary".
These two columns store what the source itself reported, with no conversion.

expires_at backs a source-provided expiry sweep. It is deliberately separate
from last_seen_at: staleness infers a listing is gone because it stopped
appearing in pulls, while expires_at is the source stating outright when the
posting ends. Sources that provide no expiry leave it NULL and continue to
rely on staleness alone.

Existing rows are all Adzuna ZA, so they backfill to annual/ZAR.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260906_listing_salary_expiry"
down_revision = "20260905_listing_last_seen"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("salary_period", sa.String(length=20), nullable=True))
    op.add_column("listings", sa.Column("salary_currency", sa.String(length=8), nullable=True))
    op.add_column("listings", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE listings SET salary_period = 'annual', salary_currency = 'ZAR'")


def downgrade() -> None:
    op.drop_column("listings", "expires_at")
    op.drop_column("listings", "salary_currency")
    op.drop_column("listings", "salary_period")
