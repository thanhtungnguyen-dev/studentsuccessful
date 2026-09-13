"""Persist bounded large-board progress across worker cycles/restarts."""

import sqlalchemy as sa
from alembic import op

revision = "e28f9a1b324c"
down_revision = "d27e8f0a213b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("live_source_states", sa.Column("retrieval_cursor", sa.String(255), nullable=True))


def downgrade():
    raise RuntimeError("Forward-only migration; restore a verified backup instead")
