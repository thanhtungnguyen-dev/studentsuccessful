"""Add private saved-search alert preferences and durable new-job events.

Revision ID: f23a9e4b7c1d
Revises: e22b4f6a8c1d
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f23a9e4b7c1d"
down_revision = "e22b4f6a8c1d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "saved_job_searches",
        sa.Column("alert_mode", sa.String(length=20), server_default=sa.text("'OFF'"), nullable=False),
    )
    op.add_column(
        "saved_job_searches",
        sa.Column("alert_enabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "saved_job_searches",
        sa.Column("alert_watermark_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "saved_job_searches",
        sa.Column("alert_evaluated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "saved_job_searches",
        sa.Column("alert_evaluated_job_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_saved_job_searches_alert_mode",
        "saved_job_searches",
        "alert_mode IN ('OFF', 'INSTANT', 'HOURLY_DIGEST', 'DAILY_DIGEST')",
    )
    op.create_check_constraint(
        "ck_saved_job_searches_alert_activation",
        "saved_job_searches",
        "(alert_mode = 'OFF' AND alert_enabled_at IS NULL AND alert_watermark_at IS NULL) "
        "OR (alert_mode <> 'OFF' AND alert_enabled_at IS NOT NULL AND alert_watermark_at IS NOT NULL)",
    )
    op.create_index(
        "idx_saved_job_searches_alert_activation",
        "saved_job_searches",
        ["alert_mode", "alert_watermark_at", "id"],
    )

    op.create_table(
        "job_alerts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("saved_search_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delivery_mode", sa.String(length=20), nullable=False),
        sa.Column(
            "delivery_state",
            sa.String(length=20),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=50), nullable=True),
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
            "delivery_mode IN ('INSTANT', 'HOURLY_DIGEST', 'DAILY_DIGEST')",
            name="ck_job_alerts_delivery_mode",
        ),
        sa.CheckConstraint(
            "delivery_state IN ('PENDING', 'DELIVERED', 'FAILED', 'SUPPRESSED')",
            name="ck_job_alerts_delivery_state",
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 3",
            name="ck_job_alerts_attempt_count",
        ),
        sa.CheckConstraint(
            "last_error_code IS NULL OR last_error_code !~ '[[:cntrl:]]'",
            name="ck_job_alerts_error_safe",
        ),
        sa.ForeignKeyConstraint(["canonical_job_id"], ["normalized_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["saved_search_id"], ["saved_job_searches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "saved_search_id",
            "canonical_job_id",
            name="uq_job_alerts_owner_search_job",
        ),
    )
    op.create_index(
        "idx_job_alerts_owner_delivered_read",
        "job_alerts",
        ["user_id", "delivered_at", "read_at", "id"],
    )
    op.create_index(
        "idx_job_alerts_due_delivery",
        "job_alerts",
        ["delivery_state", "scheduled_for", "next_retry_at", "id"],
    )
    op.create_index("idx_job_alerts_canonical_job", "job_alerts", ["canonical_job_id", "id"])


def downgrade() -> None:
    op.drop_index("idx_job_alerts_canonical_job", table_name="job_alerts")
    op.drop_index("idx_job_alerts_due_delivery", table_name="job_alerts")
    op.drop_index("idx_job_alerts_owner_delivered_read", table_name="job_alerts")
    op.drop_table("job_alerts")

    op.drop_index("idx_saved_job_searches_alert_activation", table_name="saved_job_searches")
    op.drop_constraint(
        "ck_saved_job_searches_alert_activation",
        "saved_job_searches",
        type_="check",
    )
    op.drop_constraint(
        "ck_saved_job_searches_alert_mode",
        "saved_job_searches",
        type_="check",
    )
    op.drop_column("saved_job_searches", "alert_evaluated_job_id")
    op.drop_column("saved_job_searches", "alert_evaluated_at")
    op.drop_column("saved_job_searches", "alert_watermark_at")
    op.drop_column("saved_job_searches", "alert_enabled_at")
    op.drop_column("saved_job_searches", "alert_mode")
