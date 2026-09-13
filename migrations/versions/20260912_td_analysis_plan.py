"""Add tailored_documents.analysis_plan_json.

Backs a retry of an already-analyzed document reusing its validated
AnalysisPlan (candidate_facts + job_requirements + strategy) instead of
re-running analyze_and_plan from scratch -- see app/cv_tailoring/service.py.
Nullable, no backfill: existing rows simply have no cached plan yet, which
is indistinguishable from "never analyzed" and correctly forces a fresh
analysis on their next attempt.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260912_td_analysis_plan"
down_revision = "20260906_listing_salary_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tailored_documents", sa.Column("analysis_plan_json", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("tailored_documents", "analysis_plan_json")
