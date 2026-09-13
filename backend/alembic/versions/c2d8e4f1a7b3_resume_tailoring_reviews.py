"""Add persistent user-owned resume tailoring review snapshots.

Revision ID: c2d8e4f1a7b3
Revises: f9a4c2d8e6b1
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c2d8e4f1a7b3"
down_revision = "f9a4c2d8e6b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resume_tailoring_reviews",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_resume_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_title_snapshot", sa.String(length=200), nullable=False),
        sa.Column("company_name_snapshot", sa.String(length=150), nullable=False),
        sa.Column("resume_title_snapshot", sa.String(length=150), nullable=False),
        sa.Column("resume_version_number_snapshot", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'DRAFT'"), nullable=False),
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
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'DRAFT' AND finalized_at IS NULL) OR "
            "(status = 'FINALIZED' AND finalized_at IS NOT NULL)",
            name="ck_resume_tailoring_review_finalization",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'FINALIZED')", name="ck_resume_tailoring_review_status"
        ),
        sa.CheckConstraint(
            "resume_version_number_snapshot > 0",
            name="ck_resume_tailoring_review_version_number",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["normalized_jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_resume_version_id"], ["resume_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "job_id",
            "source_resume_version_id",
            name="uq_resume_tailoring_review_user_job_version",
        ),
    )
    op.create_index("idx_resume_tailoring_reviews_user", "resume_tailoring_reviews", ["user_id"])
    op.create_index(
        "idx_resume_tailoring_reviews_job_version",
        "resume_tailoring_reviews",
        ["job_id", "source_resume_version_id"],
    )
    op.create_table(
        "resume_tailoring_review_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("requirement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requirement_name", sa.String(length=100), nullable=False),
        sa.Column("importance", sa.String(length=50), nullable=True),
        sa.Column("requirement_description", sa.Text(), nullable=True),
        sa.Column("original_draft_text", sa.String(length=300), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("limitation", sa.Text(), nullable=False),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decision", sa.String(length=20), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("user_edited_text", sa.Text(), nullable=True),
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
            "action = 'CONSIDER_ADDING_EXISTING_EVIDENCE'",
            name="ck_resume_tailoring_review_item_action",
        ),
        sa.CheckConstraint(
            "category IN ('SKILL', 'EDUCATION', 'ELIGIBILITY')",
            name="ck_resume_tailoring_review_item_category",
        ),
        sa.CheckConstraint(
            "decision IN ('PENDING', 'ACCEPTED', 'REJECTED')",
            name="ck_resume_tailoring_review_item_decision",
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_resume_tailoring_review_item_ordinal"),
        sa.CheckConstraint(
            "char_length(btrim(original_draft_text)) > 0",
            name="ck_resume_tailoring_review_item_original_draft",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(provenance) = 'array' AND jsonb_array_length(provenance) > 0",
            name="ck_resume_tailoring_review_item_provenance",
        ),
        sa.CheckConstraint(
            "char_length(btrim(reason)) > 0", name="ck_resume_tailoring_review_item_reason"
        ),
        sa.CheckConstraint(
            "char_length(btrim(requirement_name)) > 0",
            name="ck_resume_tailoring_review_item_requirement_name",
        ),
        sa.CheckConstraint(
            "user_edited_text IS NULL OR "
            "(char_length(btrim(user_edited_text)) BETWEEN 1 AND 1000)",
            name="ck_resume_tailoring_review_item_user_text",
        ),
        sa.CheckConstraint(
            "char_length(btrim(limitation)) > 0",
            name="ck_resume_tailoring_review_item_limitation",
        ),
        sa.ForeignKeyConstraint(
            ["review_id"], ["resume_tailoring_reviews.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_id", "ordinal", name="uq_resume_tailoring_review_item_ordinal"),
    )
    op.create_index(
        "idx_resume_tailoring_review_items_review",
        "resume_tailoring_review_items",
        ["review_id"],
    )
    op.create_index(
        "idx_resume_tailoring_review_items_decision",
        "resume_tailoring_review_items",
        ["review_id", "decision"],
    )


def downgrade() -> None:
    op.drop_index("idx_resume_tailoring_review_items_decision", table_name="resume_tailoring_review_items")
    op.drop_index("idx_resume_tailoring_review_items_review", table_name="resume_tailoring_review_items")
    op.drop_table("resume_tailoring_review_items")
    op.drop_index("idx_resume_tailoring_reviews_job_version", table_name="resume_tailoring_reviews")
    op.drop_index("idx_resume_tailoring_reviews_user", table_name="resume_tailoring_reviews")
    op.drop_table("resume_tailoring_reviews")
