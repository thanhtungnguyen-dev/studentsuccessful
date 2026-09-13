"""Persist explicit onboarding completion.

Revision ID: ab6c8fd54793
Revises: fa5b7ec43682
"""
import sqlalchemy as sa
from alembic import op

revision = "ab6c8fd54793"
down_revision = "fa5b7ec43682"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "onboarding_completed_at")
