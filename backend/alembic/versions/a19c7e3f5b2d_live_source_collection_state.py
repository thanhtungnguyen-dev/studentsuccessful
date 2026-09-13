"""Persist independent live-source collection schedules and health.

Revision ID: a19c7e3f5b2d
Revises: c2d8e4f1a7b3
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a19c7e3f5b2d"
down_revision = "c2d8e4f1a7b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "live_source_states",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("source_key", sa.String(length=50), nullable=False),
        sa.Column("source_family", sa.String(length=20), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("health", sa.String(length=20), server_default=sa.text("'STALE'"), nullable=False),
        sa.Column("normal_poll_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "consecutive_empty_successes", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("last_error_category", sa.String(length=50), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_http_status", sa.Integer(), nullable=True),
        sa.Column("last_jobs_seen", sa.Integer(), nullable=True),
        sa.Column("last_jobs_ingested", sa.Integer(), nullable=True),
        sa.Column("etag", sa.String(length=255), nullable=True),
        sa.Column("last_modified", sa.String(length=255), nullable=True),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_key ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,49}$'",
            name="ck_live_source_state_key_safe",
        ),
        sa.CheckConstraint(
            "source_family IN ('greenhouse', 'lever', 'ashby')",
            name="ck_live_source_state_family",
        ),
        sa.CheckConstraint(
            "health IN ('HEALTHY', 'DEGRADED', 'RATE_LIMITED', 'FAILING', 'STALE', 'DISABLED')",
            name="ck_live_source_state_health",
        ),
        sa.CheckConstraint(
            "normal_poll_interval_seconds BETWEEN 300 AND 86400",
            name="ck_live_source_state_poll_interval",
        ),
        sa.CheckConstraint(
            "consecutive_failures >= 0 AND consecutive_empty_successes >= 0",
            name="ck_live_source_state_failure_counts",
        ),
        sa.CheckConstraint(
            "last_http_status IS NULL OR last_http_status BETWEEN 100 AND 599",
            name="ck_live_source_state_http_status",
        ),
        sa.CheckConstraint(
            "last_error_category IS NULL OR "
            "(char_length(btrim(last_error_category)) > 0 AND last_error_category !~ '[[:cntrl:]]')",
            name="ck_live_source_state_error_category",
        ),
        sa.CheckConstraint(
            "(lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_live_source_state_lease_pair",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_key", name="uq_live_source_states_source_key"),
    )
    op.create_index(
        "idx_live_source_states_due", "live_source_states", ["enabled", "next_poll_at"]
    )
    op.create_index(
        "idx_live_source_states_health", "live_source_states", ["health", "last_success_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_live_source_states_health", table_name="live_source_states")
    op.drop_index("idx_live_source_states_due", table_name="live_source_states")
    op.drop_table("live_source_states")
