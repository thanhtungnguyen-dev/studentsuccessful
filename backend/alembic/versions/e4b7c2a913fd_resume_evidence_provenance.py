"""Add bounded, ordered, durable provenance for parsed resume evidence.

Revision ID: e4b7c2a913fd
Revises: d1f6f28a8c1e
"""

import sqlalchemy as sa
from alembic import op

revision = "e4b7c2a913fd"
down_revision = "d1f6f28a8c1e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Evidence was not produced before Phase 8B.  Do not invent provenance for
    # incompatible historical rows: PostgreSQL will reject a nonempty table here.
    op.add_column(
        "resume_evidence_items",
        sa.Column("ordinal", sa.Integer(), nullable=False),
    )
    op.create_check_constraint(
        "ck_resume_version_raw_text_size",
        "resume_versions",
        "raw_extracted_text IS NULL OR char_length(raw_extracted_text) <= 262144",
    )
    op.create_check_constraint(
        "ck_resume_evidence_item_category",
        "resume_evidence_items",
        "category IN ('EDUCATION', 'EXPERIENCE', 'PROJECTS', 'SKILLS', 'OTHER')",
    )
    op.create_check_constraint(
        "ck_resume_evidence_item_ordinal",
        "resume_evidence_items",
        "ordinal >= 0",
    )
    op.create_check_constraint(
        "ck_resume_evidence_item_bullet_text",
        "resume_evidence_items",
        "char_length(btrim(bullet_text)) > 0",
    )
    op.create_unique_constraint(
        "uq_resume_evidence_item_version_ordinal",
        "resume_evidence_items",
        ["resume_version_id", "ordinal"],
    )
    op.create_index(
        "idx_evidence_items_version_ordinal",
        "resume_evidence_items",
        ["resume_version_id", "ordinal"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_resume_evidence_skill_parser_confidence",
        "resume_evidence_skills",
        "parser_confidence >= 0 AND parser_confidence <= 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_resume_evidence_skill_parser_confidence",
        "resume_evidence_skills",
        type_="check",
    )
    op.drop_index("idx_evidence_items_version_ordinal", table_name="resume_evidence_items")
    op.drop_constraint(
        "uq_resume_evidence_item_version_ordinal",
        "resume_evidence_items",
        type_="unique",
    )
    op.drop_constraint(
        "ck_resume_evidence_item_bullet_text",
        "resume_evidence_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_resume_evidence_item_ordinal",
        "resume_evidence_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_resume_evidence_item_category",
        "resume_evidence_items",
        type_="check",
    )
    op.drop_constraint("ck_resume_version_raw_text_size", "resume_versions", type_="check")
    op.drop_column("resume_evidence_items", "ordinal")
