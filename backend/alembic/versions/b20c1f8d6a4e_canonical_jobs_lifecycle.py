"""Add canonical source observations and conservative job lifecycle state.

Revision ID: b20c1f8d6a4e
Revises: a19c7e3f5b2d
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b20c1f8d6a4e"
down_revision = "a19c7e3f5b2d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_source_observations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("canonical_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_source_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "source_authority",
            sa.String(length=30),
            server_default=sa.text("'TRUSTED_STRUCTURED'"),
            nullable=False,
        ),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("application_url", sa.String(length=1000), nullable=False),
        sa.Column("source_url_fingerprint", sa.CHAR(length=64), nullable=False),
        sa.Column("application_url_fingerprint", sa.CHAR(length=64), nullable=False),
        sa.Column("company_title_location_fingerprint", sa.CHAR(length=64), nullable=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("employment_type", sa.String(length=50), nullable=False),
        sa.Column(
            "career_level",
            sa.String(length=50),
            server_default=sa.text("'UNSPECIFIED'"),
            nullable=False,
        ),
        sa.Column(
            "work_mode",
            sa.String(length=30),
            server_default=sa.text("'UNSPECIFIED'"),
            nullable=False,
        ),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fact_projection", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("current_payload_hash_sha256", sa.CHAR(length=64), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "last_verified_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "consecutive_absent_successes",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_absent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "explicitly_closed",
            sa.Boolean(),
            server_default=sa.text("FALSE"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
            "source_authority IN "
            "('OFFICIAL_COMPANY', 'OFFICIAL_ATS', 'TRUSTED_STRUCTURED', "
            "'TRUSTED_AGGREGATOR', 'UNKNOWN')",
            name="ck_job_source_observation_authority",
        ),
        sa.CheckConstraint(
            "source_url ~* '^https?://[^[:space:]]+$' "
            "AND application_url ~* '^https?://[^[:space:]]+$'",
            name="ck_job_source_observation_urls",
        ),
        sa.CheckConstraint(
            "source_url_fingerprint ~ '^[0-9a-f]{64}$' "
            "AND application_url_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_job_source_observation_url_fingerprints",
        ),
        sa.CheckConstraint(
            "company_title_location_fingerprint IS NULL OR "
            "company_title_location_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_job_source_observation_exact_fingerprint",
        ),
        sa.CheckConstraint(
            "current_payload_hash_sha256 IS NULL OR "
            "current_payload_hash_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_job_source_observation_current_hash",
        ),
        sa.CheckConstraint(
            "consecutive_absent_successes >= 0",
            name="ck_job_source_observation_absence_count",
        ),
        sa.ForeignKeyConstraint(
            ["canonical_job_id"],
            ["normalized_jobs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_source_record_id"],
            ["job_source_records.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_source_record_id"),
    )
    op.create_index(
        "idx_job_source_observations_canonical",
        "job_source_observations",
        ["canonical_job_id", "explicitly_closed", "consecutive_absent_successes"],
    )
    op.create_index(
        "idx_job_source_observations_application_fingerprint",
        "job_source_observations",
        ["application_url_fingerprint"],
    )
    op.create_index(
        "idx_job_source_observations_source_fingerprint",
        "job_source_observations",
        ["source_url_fingerprint"],
    )
    op.create_index(
        "idx_job_source_observations_exact_fingerprint",
        "job_source_observations",
        ["company_title_location_fingerprint"],
    )

    op.add_column(
        "normalized_jobs",
        sa.Column(
            "lifecycle",
            sa.String(length=20),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
    )
    op.add_column(
        "normalized_jobs",
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.add_column(
        "normalized_jobs",
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.add_column(
        "normalized_jobs",
        sa.Column(
            "canonical_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.add_column(
        "normalized_jobs",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "normalized_jobs",
        sa.Column(
            "canonical_source_observation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "normalized_jobs",
        sa.Column(
            "application_source_observation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_normalized_job_lifecycle",
        "normalized_jobs",
        "lifecycle IN ('ACTIVE', 'STALE', 'CLOSED')",
    )
    op.create_foreign_key(
        "fk_normalized_jobs_canonical_source_observation",
        "normalized_jobs",
        "job_source_observations",
        ["canonical_source_observation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_normalized_jobs_application_source_observation",
        "normalized_jobs",
        "job_source_observations",
        ["application_source_observation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_normalized_jobs_lifecycle",
        "normalized_jobs",
        ["lifecycle", "last_seen_at"],
    )

    # Existing normalized jobs remain their canonical identity. The backfill
    # seeds one observation per prior source record without inventing source
    # requirement projections; a later successful observation refreshes those.
    op.execute(
        """
        INSERT INTO job_source_observations (
            canonical_job_id,
            job_source_record_id,
            source_authority,
            source_url,
            application_url,
            source_url_fingerprint,
            application_url_fingerprint,
            company_id,
            role_id,
            title,
            description,
            employment_type,
            career_level,
            work_mode,
            posted_at,
            current_payload_hash_sha256,
            first_seen_at,
            last_seen_at,
            last_verified_at,
            created_at,
            updated_at
        )
        SELECT
            normalized_jobs.id,
            normalized_jobs.job_source_record_id,
            CASE
                WHEN split_part(job_source_records.source_adapter, '.', 1)
                    IN ('greenhouse', 'lever', 'ashby')
                THEN 'OFFICIAL_ATS'
                ELSE 'TRUSTED_STRUCTURED'
            END,
            job_source_records.source_url,
            normalized_jobs.application_url,
            md5(lower(regexp_replace(job_source_records.source_url, '/+$', '')))
                || md5('phase20:' || lower(regexp_replace(job_source_records.source_url, '/+$', ''))),
            md5(lower(regexp_replace(normalized_jobs.application_url, '/+$', '')))
                || md5('phase20:' || lower(regexp_replace(normalized_jobs.application_url, '/+$', ''))),
            normalized_jobs.company_id,
            normalized_jobs.role_id,
            normalized_jobs.title,
            normalized_jobs.description,
            normalized_jobs.employment_type,
            normalized_jobs.career_level,
            normalized_jobs.work_mode,
            normalized_jobs.posted_at,
            normalized_jobs.current_payload_hash_sha256,
            normalized_jobs.discovered_at,
            normalized_jobs.last_verified_at,
            normalized_jobs.last_verified_at,
            normalized_jobs.discovered_at,
            normalized_jobs.last_verified_at
        FROM normalized_jobs
        JOIN job_source_records
          ON job_source_records.id = normalized_jobs.job_source_record_id
        ON CONFLICT (job_source_record_id) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE normalized_jobs
        SET
            first_seen_at = normalized_jobs.discovered_at,
            last_seen_at = normalized_jobs.last_verified_at,
            canonical_updated_at = normalized_jobs.last_verified_at,
            canonical_source_observation_id = job_source_observations.id,
            application_source_observation_id = job_source_observations.id
        FROM job_source_observations
        WHERE job_source_observations.canonical_job_id = normalized_jobs.id
        """
    )


def downgrade() -> None:
    op.drop_index("idx_normalized_jobs_lifecycle", table_name="normalized_jobs")
    op.drop_constraint(
        "fk_normalized_jobs_application_source_observation",
        "normalized_jobs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_normalized_jobs_canonical_source_observation",
        "normalized_jobs",
        type_="foreignkey",
    )
    op.drop_constraint("ck_normalized_job_lifecycle", "normalized_jobs", type_="check")
    op.drop_column("normalized_jobs", "application_source_observation_id")
    op.drop_column("normalized_jobs", "canonical_source_observation_id")
    op.drop_column("normalized_jobs", "closed_at")
    op.drop_column("normalized_jobs", "canonical_updated_at")
    op.drop_column("normalized_jobs", "last_seen_at")
    op.drop_column("normalized_jobs", "first_seen_at")
    op.drop_column("normalized_jobs", "lifecycle")

    op.drop_index(
        "idx_job_source_observations_exact_fingerprint",
        table_name="job_source_observations",
    )
    op.drop_index(
        "idx_job_source_observations_source_fingerprint",
        table_name="job_source_observations",
    )
    op.drop_index(
        "idx_job_source_observations_application_fingerprint",
        table_name="job_source_observations",
    )
    op.drop_index(
        "idx_job_source_observations_canonical",
        table_name="job_source_observations",
    )
    op.drop_table("job_source_observations")
