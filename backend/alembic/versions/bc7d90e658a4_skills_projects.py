"""Explicit custom skills and independent projects; reuse existing catalog/user_skills.

Revision ID: bc7d90e658a4
Revises: ab6c8fd54793
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "bc7d90e658a4"
down_revision = "ab6c8fd54793"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_custom_skills",
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
        sa.Column("value", sa.String(150), nullable=False),
        sa.Column("normalized_value", sa.String(150), nullable=False),
        sa.UniqueConstraint("user_id", "normalized_value", name="uq_user_custom_skill"),
        sa.CheckConstraint(
            "length(btrim(value)) > 0 AND length(btrim(normalized_value)) > 0",
            name="ck_user_custom_skill_nonblank",
        ),
    )
    op.create_table(
        "projects",
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
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("project_url", sa.String(500)),
        sa.Column("repository_url", sa.String(500)),
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
        sa.CheckConstraint("length(btrim(title)) > 0", name="ck_project_title_nonblank"),
        sa.CheckConstraint("length(description) <= 5000", name="ck_project_description_length"),
    )
    op.create_index("idx_projects_user", "projects", ["user_id"])
    op.create_table(
        "project_skills",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "skill_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("skills.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    op.create_table(
        "project_custom_skills",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value", sa.String(150), nullable=False),
        sa.Column("normalized_value", sa.String(150), nullable=False),
        sa.UniqueConstraint("project_id", "normalized_value", name="uq_project_custom_skill"),
        sa.CheckConstraint(
            "length(btrim(value)) > 0 AND length(btrim(normalized_value)) > 0",
            name="ck_project_custom_skill_nonblank",
        ),
    )


def downgrade():
    op.drop_table("project_custom_skills")
    op.drop_table("project_skills")
    op.drop_index("idx_projects_user", table_name="projects")
    op.drop_table("projects")
    op.drop_table("user_custom_skills")
