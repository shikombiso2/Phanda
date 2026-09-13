"""Widen listings.apply_target from VARCHAR(1024) to TEXT.

Backs DPSA circular listings: apply_target there is the raw APPLICATIONS
field text (a postal address, hand-delivery instructions, sometimes several
sentences) rather than a URL or a single email address like every other
source stores. A real ingestion run against five live circulars hit
StringDataRightTruncation on at least one department's APPLICATIONS text.

Widening the column, not truncating at the adapter level, because: DPSA's
apply_target is the ONLY instruction a user gets for a manual (non-clickable)
apply method -- truncating it risks silently cutting off the actual email
address or the last line of a multi-part instruction, which is actively
harmful for the one source that needs this field to be complete. Postgres
TEXT and VARCHAR(n) have identical storage and performance (VARCHAR(n) is
TEXT plus a length check) -- there is no cost to widening, and every other
source's apply_target (a URL or an email address) is unaffected; none of
them approach the old 1024-char limit, let alone need it enforced.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260913_apply_target_text"
down_revision = "20260913_apply_method_manual"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("listings", "apply_target", type_=sa.Text(), existing_type=sa.String(length=1024), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("listings", "apply_target", type_=sa.String(length=1024), existing_type=sa.Text(), existing_nullable=False)
