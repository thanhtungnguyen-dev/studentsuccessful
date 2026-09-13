"""Add private manual application tracking invariants.

Revision ID: a24b8d1e6f20
Revises: f23a9e4b7c1d
"""

import sqlalchemy as sa
from alembic import op

revision = "a24b8d1e6f20"
down_revision = "f23a9e4b7c1d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("job_title_snapshot", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column("company_name_snapshot", sa.String(length=150), nullable=True),
    )
    op.alter_column(
        "applications",
        "current_status",
        existing_type=sa.String(length=50),
        existing_nullable=False,
        server_default=sa.text("'APPLIED'"),
    )
    op.drop_constraint("applications_job_id_fkey", "applications", type_="foreignkey")
    op.create_foreign_key(
        "applications_job_id_fkey",
        "applications",
        "normalized_jobs",
        ["job_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "applications_resume_version_id_fkey",
        "applications",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "applications_resume_version_id_fkey",
        "applications",
        "resume_versions",
        ["resume_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_application_current_status",
        "applications",
        "current_status IN ('APPLIED', 'INTERVIEW', 'OFFER', 'REJECTED', 'WITHDRAWN')",
    )
    op.create_check_constraint(
        "ck_application_notes_length",
        "applications",
        "notes IS NULL OR char_length(notes) <= 2000",
    )
    op.create_index(
        "idx_applications_owner_updated",
        "applications",
        ["user_id", "updated_at", "id"],
    )

    op.create_check_constraint(
        "ck_application_history_new_status",
        "application_status_histories",
        "new_status IN ('APPLIED', 'INTERVIEW', 'OFFER', 'REJECTED', 'WITHDRAWN')",
    )
    op.create_check_constraint(
        "ck_application_history_previous_status",
        "application_status_histories",
        "previous_status IS NULL OR previous_status IN "
        "('APPLIED', 'INTERVIEW', 'OFFER', 'REJECTED', 'WITHDRAWN')",
    )
    op.create_check_constraint(
        "ck_application_history_status_change",
        "application_status_histories",
        "previous_status IS NULL OR previous_status <> new_status",
    )
    op.create_check_constraint(
        "ck_application_history_notes_length",
        "application_status_histories",
        "notes IS NULL OR char_length(notes) <= 2000",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_application_history_notes_length",
        "application_status_histories",
        type_="check",
    )
    op.drop_constraint(
        "ck_application_history_status_change",
        "application_status_histories",
        type_="check",
    )
    op.drop_constraint(
        "ck_application_history_previous_status",
        "application_status_histories",
        type_="check",
    )
    op.drop_constraint(
        "ck_application_history_new_status",
        "application_status_histories",
        type_="check",
    )
    op.drop_index("idx_applications_owner_updated", table_name="applications")
    op.drop_constraint("ck_application_notes_length", "applications", type_="check")
    op.drop_constraint("ck_application_current_status", "applications", type_="check")
    op.drop_constraint(
        "applications_resume_version_id_fkey",
        "applications",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "applications_resume_version_id_fkey",
        "applications",
        "resume_versions",
        ["resume_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint("applications_job_id_fkey", "applications", type_="foreignkey")
    op.create_foreign_key(
        "applications_job_id_fkey",
        "applications",
        "normalized_jobs",
        ["job_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column(
        "applications",
        "current_status",
        existing_type=sa.String(length=50),
        existing_nullable=False,
        server_default=None,
    )
    op.drop_column("applications", "company_name_snapshot")
    op.drop_column("applications", "job_title_snapshot")
