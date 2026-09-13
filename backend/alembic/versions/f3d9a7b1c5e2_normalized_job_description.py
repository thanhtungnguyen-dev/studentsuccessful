"""Add an optional normalized description for shared job browsing.

Revision ID: f3d9a7b1c5e2
Revises: e4b7c2a913fd
"""

import sqlalchemy as sa
from alembic import op

revision = "f3d9a7b1c5e2"
down_revision = "e4b7c2a913fd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Historical normalized jobs have no reliable description to backfill.
    op.add_column("normalized_jobs", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("normalized_jobs", "description")
