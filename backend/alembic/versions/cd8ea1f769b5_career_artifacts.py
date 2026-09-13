"""User-owned linked resume artifacts; no seeds or inferred backfill."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "cd8ea1f769b5"
down_revision = "bc7d90e658a4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "career_artifacts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("artifact_type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("external_url", sa.String(500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("artifact_type = 'RESUME'", name="ck_artifact_type"),
        sa.CheckConstraint("length(btrim(title)) > 0", name="ck_artifact_title"),
        sa.CheckConstraint("external_url ~ '^https?://'", name="ck_artifact_url_scheme"),
    )
    op.create_index("idx_career_artifacts_user", "career_artifacts", ["user_id"])


def downgrade():
    op.drop_index("idx_career_artifacts_user", table_name="career_artifacts")
    op.drop_table("career_artifacts")
