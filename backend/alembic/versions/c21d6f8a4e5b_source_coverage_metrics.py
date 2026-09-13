"""Expand public source families and retain small aggregate value metrics.

Revision ID: c21d6f8a4e5b
Revises: b20c1f8d6a4e
"""

import sqlalchemy as sa
from alembic import op

revision = "c21d6f8a4e5b"
down_revision = "b20c1f8d6a4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_live_source_state_family",
        "live_source_states",
        type_="check",
    )
    for name in (
        "total_collection_attempts",
        "total_collection_failures",
        "total_jobs_observed",
        "total_jobs_ingested",
        "total_new_canonical_jobs",
        "total_duplicate_contributions",
        "total_internship_or_coop_contributions",
        "total_official_apply_urls",
    ):
        op.add_column(
            "live_source_states",
            sa.Column(name, sa.Integer(), server_default=sa.text("0"), nullable=False),
        )
    op.add_column(
        "live_source_states",
        sa.Column("last_new_canonical_job_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_live_source_state_family",
        "live_source_states",
        "source_family IN ('greenhouse', 'lever', 'ashby', 'smartrecruiters', 'rss')",
    )
    op.create_check_constraint(
        "ck_live_source_state_value_metrics",
        "live_source_states",
        "total_collection_attempts >= 0 "
        "AND total_collection_failures >= 0 "
        "AND total_jobs_observed >= 0 "
        "AND total_jobs_ingested >= 0 "
        "AND total_new_canonical_jobs >= 0 "
        "AND total_duplicate_contributions >= 0 "
        "AND total_internship_or_coop_contributions >= 0 "
        "AND total_official_apply_urls >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_live_source_state_value_metrics",
        "live_source_states",
        type_="check",
    )
    op.drop_constraint(
        "ck_live_source_state_family",
        "live_source_states",
        type_="check",
    )
    op.drop_column("live_source_states", "last_new_canonical_job_at")
    for name in (
        "total_official_apply_urls",
        "total_internship_or_coop_contributions",
        "total_duplicate_contributions",
        "total_new_canonical_jobs",
        "total_jobs_ingested",
        "total_jobs_observed",
        "total_collection_failures",
        "total_collection_attempts",
    ):
        op.drop_column("live_source_states", name)
    op.create_check_constraint(
        "ck_live_source_state_family",
        "live_source_states",
        "source_family IN ('greenhouse', 'lever', 'ashby')",
    )
