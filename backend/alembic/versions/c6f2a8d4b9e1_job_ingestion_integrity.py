"""Harden persisted job-source identity, URLs, and canonical snapshot hashes.

Revision ID: c6f2a8d4b9e1
Revises: f3d9a7b1c5e2
"""

from alembic import op

revision = "c6f2a8d4b9e1"
down_revision = "f3d9a7b1c5e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_job_source_adapter_safe",
        "job_source_records",
        "btrim(source_adapter) <> '' AND source_adapter !~ '[[:cntrl:]]'",
    )
    op.create_check_constraint(
        "ck_job_source_external_id_safe",
        "job_source_records",
        "btrim(external_id) <> '' AND external_id !~ '[[:cntrl:]]'",
    )
    op.create_check_constraint(
        "ck_job_source_url_http",
        "job_source_records",
        "source_url ~* '^https?://[^[:space:]]+$'",
    )
    op.create_check_constraint(
        "ck_job_snapshot_hash_sha256",
        "raw_job_snapshots",
        "payload_hash_sha256 ~ '^[0-9a-f]{64}$'",
    )
    op.create_check_constraint(
        "ck_normalized_job_application_url_http",
        "normalized_jobs",
        "application_url ~* '^https?://[^[:space:]]+$'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_normalized_job_application_url_http", "normalized_jobs", type_="check"
    )
    op.drop_constraint("ck_job_snapshot_hash_sha256", "raw_job_snapshots", type_="check")
    op.drop_constraint("ck_job_source_url_http", "job_source_records", type_="check")
    op.drop_constraint("ck_job_source_external_id_safe", "job_source_records", type_="check")
    op.drop_constraint("ck_job_source_adapter_safe", "job_source_records", type_="check")
