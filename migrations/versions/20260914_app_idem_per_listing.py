"""Widen applications' idempotency uniqueness to (user_id, listing_id, idempotency_key).

Previously (user_id, idempotency_key) alone: a client-generated key reused
across two different listings for the same user would silently return the
FIRST listing's application on the second apply call, instead of creating a
second row -- app/applications/router.py's dedup check already made this
mistake at the query level too (fixed in the same change), but the old
DB-level UniqueConstraint would still have rejected a correct second insert
even after that fix. Confirmed today's frontend always generates a fresh
crypto.randomUUID() per apply call, so this was never live-exploitable, but
it's a real correctness gap worth closing at both layers.
"""
from alembic import op

revision = "20260914_app_idem_per_listing"
down_revision = "20260913_listing_location_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_application_idempotency", "applications", type_="unique")
    op.create_unique_constraint(
        "uq_application_idempotency", "applications", ["user_id", "listing_id", "idempotency_key"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_application_idempotency", "applications", type_="unique")
    op.create_unique_constraint("uq_application_idempotency", "applications", ["user_id", "idempotency_key"])
