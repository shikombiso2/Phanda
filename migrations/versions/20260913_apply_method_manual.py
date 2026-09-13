"""Add 'manual' to the applymethod enum.

Backs DPSA circular listings, where no automated submission path exists at
all (the applicant must complete and submit a Z83 form themselves entirely
outside Phanda) -- distinct from ats_link, which still means a real external
apply page exists to click through to.

Note on transactionality: PostgreSQL (16, per docker-compose.yml) allows
ALTER TYPE ... ADD VALUE to run inside a transaction block, but the new
value cannot be *used* (e.g. in an INSERT/UPDATE) within that same
transaction. This migration only adds the value and writes no data, so it
runs safely inside Alembic's normal single-transaction migration -- no
autocommit_block() or op.execute("COMMIT") workaround needed. Confirmed by
running it live (see the ingestion report) rather than assumed.

downgrade() is a no-op: PostgreSQL has no ALTER TYPE ... DROP VALUE at all.
Reverting would require rebuilding the enum type from scratch (rename old,
create new, migrate every column using it, drop old) -- not worth the risk
for a downgrade path this schema has never actually needed to exercise.
"""
from alembic import op

revision = "20260913_apply_method_manual"
down_revision = "20260913_cv_extracted_skills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE applymethod ADD VALUE IF NOT EXISTS 'manual'")


def downgrade() -> None:
    raise NotImplementedError("PostgreSQL cannot drop a value from an enum type; see module docstring.")
