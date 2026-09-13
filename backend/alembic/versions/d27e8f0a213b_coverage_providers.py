"""Allow documented Workable and Teamtailor sources in the existing collector.
Revision ID: d27e8f0a213b
Revises: c26d7e9f102a
"""

from alembic import op

revision = "d27e8f0a213b"
down_revision = "c26d7e9f102a"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_live_source_state_family", "live_source_states", type_="check")
    op.create_check_constraint(
        "ck_live_source_state_family",
        "live_source_states",
        "source_family IN ('greenhouse', 'lever', 'ashby', 'smartrecruiters', 'rss', 'recruitee', 'personio', 'jsonld', 'workable', 'teamtailor')",
    )


def downgrade():
    raise RuntimeError("Forward-only migration; restore a verified backup instead")
