"""Add cv_versions.extracted_skills.

Backs CV-based skill matching as a second, independent input to
skill_compatibility() alongside profile.skills -- never merged into it. See
app/core/models.py's CvVersion.extracted_skills docstring for the full
rationale. NOT NULL with a default of '{}', no data backfill needed: an
existing CV version simply has no extracted skills yet, indistinguishable
from "extracted nothing", which is the correct behaviour until it's
re-processed.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260913_cv_extracted_skills"
down_revision = "20260912_td_analysis_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cv_versions",
        sa.Column("extracted_skills", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
    )
    op.alter_column("cv_versions", "extracted_skills", server_default=None)


def downgrade() -> None:
    op.drop_column("cv_versions", "extracted_skills")
