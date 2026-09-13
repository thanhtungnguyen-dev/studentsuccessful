"""Add durable worker heartbeats and leases for production monitoring.

Revision ID: b25c6d4e8f10
Revises: a24b8d1e6f20
Create Date: 2026-09-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b25c6d4e8f10"
down_revision = "a24b8d1e6f20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_name", sa.String(length=32), nullable=False),
        sa.Column(
            "worker_state",
            sa.String(length=12),
            nullable=False,
            server_default=sa.text("'STOPPED'"),
        ),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "worker_name IN ('collector', 'alert-worker')",
            name="ck_worker_heartbeat_name",
        ),
        sa.CheckConstraint(
            "worker_state IN ('RUNNING', 'STOPPED')",
            name="ck_worker_heartbeat_state",
        ),
        sa.PrimaryKeyConstraint("worker_name"),
    )
    op.create_index("idx_worker_heartbeats_lease", "worker_heartbeats", ["lease_expires_at"])


def downgrade() -> None:
    op.drop_index("idx_worker_heartbeats_lease", table_name="worker_heartbeats")
    op.drop_table("worker_heartbeats")
