"""Preserve employment facts and require chronological dates.

Revision ID: d83f5ca21460
Revises: c72e4b9d103f
"""

from alembic import op

revision = "d83f5ca21460"
down_revision = "c72e4b9d103f"
branch_labels = None
depends_on = None


def upgrade():
    # PostgreSQL validates existing rows; incompatible facts block the transaction.
    # Never swap dates, repair records or delete user data.
    op.create_check_constraint("ck_employment_date_order", "employment_records", "end_date IS NULL OR end_date >= start_date")


def downgrade():
    op.drop_constraint("ck_employment_date_order", "employment_records", type_="check")
