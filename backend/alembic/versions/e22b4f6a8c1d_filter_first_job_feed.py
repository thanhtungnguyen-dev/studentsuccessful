"""Add private job-feed state and structured saved searches.

Revision ID: e22b4f6a8c1d
Revises: c21d6f8a4e5b
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e22b4f6a8c1d"
down_revision = "c21d6f8a4e5b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_normalized_jobs_feed_newest",
        "normalized_jobs",
        [sa.text("first_seen_at DESC"), sa.text("id DESC")],
        unique=False,
        postgresql_where=sa.text("is_active IS TRUE"),
    )
    op.create_table(
        "user_job_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("saved", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("hidden", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["canonical_job_id"], ["normalized_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "canonical_job_id", name="uq_user_job_states_owner_job"),
    )
    op.create_index(
        "idx_user_job_states_owner_hidden_job",
        "user_job_states",
        ["user_id", "hidden", "canonical_job_id"],
    )
    op.create_index(
        "idx_user_job_states_owner_saved_job",
        "user_job_states",
        ["user_id", "saved", "canonical_job_id"],
    )

    op.create_table(
        "saved_job_searches",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 100 AND name !~ '[[:cntrl:]]'",
            name="ck_saved_job_searches_name_safe",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(criteria) = 'object'",
            name="ck_saved_job_searches_criteria_object",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_saved_job_searches_owner_updated",
        "saved_job_searches",
        ["user_id", "updated_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("idx_saved_job_searches_owner_updated", table_name="saved_job_searches")
    op.drop_table("saved_job_searches")
    op.drop_index("idx_user_job_states_owner_saved_job", table_name="user_job_states")
    op.drop_index("idx_user_job_states_owner_hidden_job", table_name="user_job_states")
    op.drop_table("user_job_states")
    op.drop_index("idx_normalized_jobs_feed_newest", table_name="normalized_jobs")
