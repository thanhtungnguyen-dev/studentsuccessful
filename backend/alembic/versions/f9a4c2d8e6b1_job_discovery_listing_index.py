"""Add the active catalog index used by deterministic discovery pages.

Revision ID: f9a4c2d8e6b1
Revises: e7d1b9f4a2c3
"""

import sqlalchemy as sa
from alembic import op

revision = "f9a4c2d8e6b1"
down_revision = "e7d1b9f4a2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_normalized_jobs_active_listing",
        "normalized_jobs",
        [
            sa.text("posted_at DESC NULLS LAST"),
            sa.text("discovered_at DESC"),
            "id",
        ],
        postgresql_where=sa.text("is_active IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index("idx_normalized_jobs_active_listing", table_name="normalized_jobs")
