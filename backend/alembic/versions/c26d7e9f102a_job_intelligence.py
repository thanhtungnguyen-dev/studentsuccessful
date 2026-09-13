"""Durable discovery, bounded replay evidence and canonical field provenance.

Revision ID: c26d7e9f102a
Revises: b25c6d4e8f10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "c26d7e9f102a"
down_revision = "b25c6d4e8f10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_registry",
        sa.Column("source_key", sa.String(50), primary_key=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("identity", sa.String(1000), nullable=False),
        sa.Column("configuration", JSONB, nullable=False),
        sa.Column("origin", sa.String(12), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("discovered_from", sa.String(1000)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("provider", "identity", name="uq_source_registry_identity"),
        sa.CheckConstraint(
            "origin IN ('CONFIGURED', 'DISCOVERED')", name="ck_source_registry_origin"
        ),
    )
    op.create_table(
        "source_discovery_work",
        sa.Column("url_hash", sa.String(64), primary_key=True),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("company", sa.String(150), nullable=False),
        sa.Column("parent_source", sa.String(50), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "due_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("result_source", sa.String(50)),
        sa.CheckConstraint(
            "state IN ('PENDING', 'VERIFIED', 'UNKNOWN', 'FAILED')", name="ck_discovery_state"
        ),
        sa.CheckConstraint("attempts BETWEEN 0 AND 3", name="ck_discovery_attempts"),
    )
    op.create_index("idx_discovery_due", "source_discovery_work", ["state", "due_at"])
    op.create_table(
        "source_fetch_evidence",
        sa.Column("source_key", sa.String(50), primary_key=True),
        sa.Column("content_hash", sa.String(64), primary_key=True),
        sa.Column("parser_version", sa.String(20), nullable=False),
        sa.Column("configuration", JSONB, nullable=False),
        sa.Column("pages", JSONB, nullable=False),
        sa.Column(
            "first_fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_table(
        "job_change_events",
        sa.Column("event_key", sa.String(64), primary_key=True),
        sa.Column(
            "job_id",
            UUID(as_uuid=True),
            sa.ForeignKey("normalized_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "observation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("job_source_observations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("previous_hash", sa.String(64)),
        sa.Column("current_hash", sa.String(64), nullable=False),
        sa.Column("changed_fields", JSONB, nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("idx_job_changes_job_time", "job_change_events", ["job_id", "observed_at"])
    op.add_column(
        "live_source_states",
        sa.Column("unchanged_successes", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("live_source_states", sa.Column("last_change_at", sa.DateTime(timezone=True)))
    op.add_column("live_source_states", sa.Column("last_content_hash", sa.String(64)))
    op.add_column("normalized_jobs", sa.Column("field_provenance", JSONB))
    op.drop_constraint("ck_live_source_state_family", "live_source_states", type_="check")
    op.create_check_constraint(
        "ck_live_source_state_family",
        "live_source_states",
        "source_family IN ('greenhouse', 'lever', 'ashby', 'smartrecruiters', 'rss', 'recruitee', 'personio', 'jsonld')",
    )


def downgrade():
    raise RuntimeError("Forward-only migration; restore a verified backup instead")
