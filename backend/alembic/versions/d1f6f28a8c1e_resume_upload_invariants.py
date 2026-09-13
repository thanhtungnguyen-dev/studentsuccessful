"""Add durable invariants required before managed resume uploads.

Revision ID: d1f6f28a8c1e
Revises: cd8ea1f769b5
"""

from alembic import op

revision = "d1f6f28a8c1e"
down_revision = "cd8ea1f769b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing incompatible rows deliberately make the migration fail; no facts are guessed or repaired.
    op.create_check_constraint(
        "ck_resume_version_number_positive", "resume_versions", "version_number > 0"
    )
    op.create_check_constraint(
        "ck_resume_version_file_size",
        "resume_versions",
        "file_size_bytes > 0 AND file_size_bytes <= 5242880",
    )
    op.create_check_constraint(
        "ck_resume_version_file_format",
        "resume_versions",
        "file_format IN ('PDF', 'DOCX')",
    )
    op.create_check_constraint(
        "ck_resume_version_parse_status",
        "resume_versions",
        "parse_status IN ('PENDING', 'PARSED_SUCCESS', 'PARSE_FAILED', 'USER_MODIFIED')",
    )
    op.create_check_constraint(
        "ck_resume_version_sha256",
        "resume_versions",
        "file_hash_sha256 ~ '^[0-9a-f]{64}$'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_resume_version_sha256", "resume_versions", type_="check")
    op.drop_constraint("ck_resume_version_parse_status", "resume_versions", type_="check")
    op.drop_constraint("ck_resume_version_file_format", "resume_versions", type_="check")
    op.drop_constraint("ck_resume_version_file_size", "resume_versions", type_="check")
    op.drop_constraint("ck_resume_version_number_positive", "resume_versions", type_="check")
