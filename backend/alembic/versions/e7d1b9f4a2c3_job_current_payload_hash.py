"""Track the currently applied canonical job snapshot without rewriting history.

Revision ID: e7d1b9f4a2c3
Revises: c6f2a8d4b9e1
"""

import sqlalchemy as sa
from alembic import op

revision = "e7d1b9f4a2c3"
down_revision = "c6f2a8d4b9e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "normalized_jobs",
        sa.Column("current_payload_hash_sha256", sa.CHAR(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_normalized_job_current_hash_sha256",
        "normalized_jobs",
        "current_payload_hash_sha256 IS NULL OR "
        "current_payload_hash_sha256 ~ '^[0-9a-f]{64}$'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_normalized_job_current_hash_sha256", "normalized_jobs", type_="check"
    )
    op.drop_column("normalized_jobs", "current_payload_hash_sha256")
