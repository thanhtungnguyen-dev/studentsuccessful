"""Job source, snapshot, normalized job, and requirement entities."""

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.app.models.base import Base, generate_uuid, utc_now


class LiveSourceHealth:
    """Persistent collector health values for one configured public source."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    FAILING = "FAILING"
    STALE = "STALE"
    DISABLED = "DISABLED"

    ALL = (HEALTHY, DEGRADED, RATE_LIMITED, FAILING, STALE, DISABLED)


class JobLifecycle:
    """Canonical job states; NEW is a deterministic presentation window."""

    ACTIVE = "ACTIVE"
    STALE = "STALE"
    CLOSED = "CLOSED"

    ALL = (ACTIVE, STALE, CLOSED)


class SavedSearchAlertMode:
    """Delivery choices for new jobs matched by one private saved search."""

    OFF = "OFF"
    INSTANT = "INSTANT"
    HOURLY_DIGEST = "HOURLY_DIGEST"
    DAILY_DIGEST = "DAILY_DIGEST"

    ALL = (OFF, INSTANT, HOURLY_DIGEST, DAILY_DIGEST)


class JobAlertDeliveryState:
    """Durable in-app delivery states for a private new-job alert."""

    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    SUPPRESSED = "SUPPRESSED"

    ALL = (PENDING, DELIVERED, FAILED, SUPPRESSED)


class JobSourceAuthority:
    """Generic provenance classes used when resolving canonical job facts."""

    OFFICIAL_COMPANY = "OFFICIAL_COMPANY"
    OFFICIAL_ATS = "OFFICIAL_ATS"
    TRUSTED_STRUCTURED = "TRUSTED_STRUCTURED"
    TRUSTED_AGGREGATOR = "TRUSTED_AGGREGATOR"
    UNKNOWN = "UNKNOWN"

    ALL = (
        OFFICIAL_COMPANY,
        OFFICIAL_ATS,
        TRUSTED_STRUCTURED,
        TRUSTED_AGGREGATOR,
        UNKNOWN,
    )


class LiveSourceState(Base):
    """Durable scheduling and bounded public-source health state.

    This has no relationship to individual source posting rows.  It records the
    configured board's collection lifecycle only, so a failed fetch never
    changes the lifecycle of an existing job.
    """

    __tablename__ = "live_source_states"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    source_key = Column(String(50), nullable=False)
    source_family = Column(String(20), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    health = Column(
        String(20), nullable=False, default=LiveSourceHealth.STALE,
        server_default=text("'STALE'"),
    )
    normal_poll_interval_seconds = Column(Integer, nullable=False)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_completed_at = Column(DateTime(timezone=True), nullable=True)
    next_poll_at = Column(DateTime(timezone=True), nullable=True)
    consecutive_failures = Column(Integer, nullable=False, default=0, server_default=text("0"))
    consecutive_empty_successes = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    last_error_category = Column(String(50), nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    last_http_status = Column(Integer, nullable=True)
    last_jobs_seen = Column(Integer, nullable=True)
    last_jobs_ingested = Column(Integer, nullable=True)
    total_collection_attempts = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    total_collection_failures = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    total_jobs_observed = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    total_jobs_ingested = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    total_new_canonical_jobs = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    total_duplicate_contributions = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    total_internship_or_coop_contributions = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    total_official_apply_urls = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    last_new_canonical_job_at = Column(DateTime(timezone=True), nullable=True)
    etag = Column(String(255), nullable=True)
    last_modified = Column(String(255), nullable=True)
    lease_token = Column(UUID(as_uuid=True), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=utc_now, nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at = Column(
        DateTime(timezone=True), default=utc_now, nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint(
            "source_key ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,49}$'",
            name="ck_live_source_state_key_safe",
        ),
        CheckConstraint(
            "source_family IN ('greenhouse', 'lever', 'ashby', 'smartrecruiters', 'rss')",
            name="ck_live_source_state_family",
        ),
        CheckConstraint(
            "health IN ('HEALTHY', 'DEGRADED', 'RATE_LIMITED', 'FAILING', 'STALE', 'DISABLED')",
            name="ck_live_source_state_health",
        ),
        CheckConstraint(
            "normal_poll_interval_seconds BETWEEN 300 AND 86400",
            name="ck_live_source_state_poll_interval",
        ),
        CheckConstraint(
            "consecutive_failures >= 0 AND consecutive_empty_successes >= 0",
            name="ck_live_source_state_failure_counts",
        ),
        CheckConstraint(
            "total_collection_attempts >= 0 "
            "AND total_collection_failures >= 0 "
            "AND total_jobs_observed >= 0 "
            "AND total_jobs_ingested >= 0 "
            "AND total_new_canonical_jobs >= 0 "
            "AND total_duplicate_contributions >= 0 "
            "AND total_internship_or_coop_contributions >= 0 "
            "AND total_official_apply_urls >= 0",
            name="ck_live_source_state_value_metrics",
        ),
        CheckConstraint(
            "last_http_status IS NULL OR last_http_status BETWEEN 100 AND 599",
            name="ck_live_source_state_http_status",
        ),
        CheckConstraint(
            "last_error_category IS NULL OR "
            "(char_length(btrim(last_error_category)) > 0 AND last_error_category !~ '[[:cntrl:]]')",
            name="ck_live_source_state_error_category",
        ),
        CheckConstraint(
            "(lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_live_source_state_lease_pair",
        ),
        UniqueConstraint("source_key", name="uq_live_source_states_source_key"),
        Index("idx_live_source_states_due", "enabled", "next_poll_at"),
        Index("idx_live_source_states_health", "health", "last_success_at"),
    )


class JobSourceRecord(Base):
    __tablename__ = "job_source_records"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    source_adapter = Column(String(50), nullable=False)
    external_id = Column(String(255), nullable=False)
    source_url = Column(String(1000), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint("source_adapter", "external_id", name="uq_job_source_external"),
        CheckConstraint(
            "btrim(source_adapter) <> '' AND source_adapter !~ '[[:cntrl:]]'",
            name="ck_job_source_adapter_safe",
        ),
        CheckConstraint(
            "btrim(external_id) <> '' AND external_id !~ '[[:cntrl:]]'",
            name="ck_job_source_external_id_safe",
        ),
        CheckConstraint(
            "source_url ~* '^https?://[^[:space:]]+$'",
            name="ck_job_source_url_http",
        ),
    )


class RawJobSnapshot(Base):
    __tablename__ = "raw_job_snapshots"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    job_source_record_id = Column(
        UUID(as_uuid=True), ForeignKey("job_source_records.id", ondelete="CASCADE"), nullable=False
    )
    raw_payload = Column(JSONB, nullable=False)
    payload_hash_sha256 = Column(CHAR(64), nullable=False)
    fetched_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint(
            "job_source_record_id", "payload_hash_sha256", name="uq_job_snapshot_hash"
        ),
        CheckConstraint(
            "payload_hash_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_job_snapshot_hash_sha256",
        ),
    )


class NormalizedJob(Base):
    __tablename__ = "normalized_jobs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    job_source_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("job_source_records.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    role_id = Column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    employment_type = Column(String(50), nullable=False)
    career_level = Column(
        String(50), nullable=False, default="UNSPECIFIED", server_default=text("'UNSPECIFIED'")
    )
    work_mode = Column(
        String(30), nullable=False, default="UNSPECIFIED", server_default=text("'UNSPECIFIED'")
    )
    application_url = Column(String(1000), nullable=False)
    # Private ingestion state. Legacy Phase 9 records remain NULL until the
    # first successful Phase 10 ingestion applies a canonical snapshot.
    current_payload_hash_sha256 = Column(CHAR(64), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    lifecycle = Column(
        String(20),
        nullable=False,
        default=JobLifecycle.ACTIVE,
        server_default=text("'ACTIVE'"),
    )
    posted_at = Column(DateTime(timezone=True), nullable=True)
    discovered_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    last_verified_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    # discovered_at remains the historical compatibility field. Phase 20
    # introduces explicit canonical freshness timestamps without rewriting it.
    first_seen_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    last_seen_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    canonical_updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    closed_at = Column(DateTime(timezone=True), nullable=True)
    canonical_source_observation_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "job_source_observations.id",
            ondelete="SET NULL",
            name="fk_normalized_jobs_canonical_source_observation",
            use_alter=True,
        ),
        nullable=True,
    )
    application_source_observation_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "job_source_observations.id",
            ondelete="SET NULL",
            name="fk_normalized_jobs_application_source_observation",
            use_alter=True,
        ),
        nullable=True,
    )

    __table_args__ = (
        Index("idx_normalized_jobs_role_active", "role_id", "is_active"),
        Index("idx_normalized_jobs_company", "company_id"),
        Index("idx_normalized_jobs_discovered", "discovered_at"),
        Index(
            "idx_normalized_jobs_active_listing",
            posted_at.desc().nulls_last(),
            discovered_at.desc(),
            id,
            postgresql_where=is_active.is_(True),
        ),
        Index(
            "idx_normalized_jobs_feed_newest",
            first_seen_at.desc(),
            id.desc(),
            postgresql_where=is_active.is_(True),
        ),
        CheckConstraint(
            "application_url ~* '^https?://[^[:space:]]+$'",
            name="ck_normalized_job_application_url_http",
        ),
        CheckConstraint(
            "current_payload_hash_sha256 IS NULL OR "
            "current_payload_hash_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_normalized_job_current_hash_sha256",
        ),
        CheckConstraint(
            "lifecycle IN ('ACTIVE', 'STALE', 'CLOSED')",
            name="ck_normalized_job_lifecycle",
        ),
        Index("idx_normalized_jobs_lifecycle", "lifecycle", "last_seen_at"),
    )


class UserJobState(Base):
    """Private, per-user interaction state for one shared canonical job."""

    __tablename__ = "user_job_states"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    canonical_job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("normalized_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    saved = Column(Boolean, nullable=False, default=False, server_default=text("FALSE"))
    hidden = Column(Boolean, nullable=False, default=False, server_default=text("FALSE"))
    viewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "canonical_job_id", name="uq_user_job_states_owner_job"),
        Index(
            "idx_user_job_states_owner_hidden_job",
            "user_id",
            "hidden",
            "canonical_job_id",
        ),
        Index(
            "idx_user_job_states_owner_saved_job",
            "user_id",
            "saved",
            "canonical_job_id",
        ),
    )


class SavedJobSearch(Base):
    """A user's validated structured job-feed criteria."""

    __tablename__ = "saved_job_searches"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(100), nullable=False)
    criteria = Column(JSONB, nullable=False)
    alert_mode = Column(
        String(20),
        nullable=False,
        default=SavedSearchAlertMode.OFF,
        server_default=text("'OFF'"),
    )
    alert_enabled_at = Column(DateTime(timezone=True), nullable=True)
    # This is the activation boundary. Jobs discovered before it never backfill.
    alert_watermark_at = Column(DateTime(timezone=True), nullable=True)
    # The pair is a durable, stable reconciliation cursor ordered by canonical
    # first_seen_at and canonical job id. It is distinct from activation.
    alert_evaluated_at = Column(DateTime(timezone=True), nullable=True)
    alert_evaluated_job_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 100 AND name !~ '[[:cntrl:]]'",
            name="ck_saved_job_searches_name_safe",
        ),
        CheckConstraint(
            "jsonb_typeof(criteria) = 'object'",
            name="ck_saved_job_searches_criteria_object",
        ),
        CheckConstraint(
            "alert_mode IN ('OFF', 'INSTANT', 'HOURLY_DIGEST', 'DAILY_DIGEST')",
            name="ck_saved_job_searches_alert_mode",
        ),
        CheckConstraint(
            "(alert_mode = 'OFF' AND alert_enabled_at IS NULL AND alert_watermark_at IS NULL) "
            "OR (alert_mode <> 'OFF' AND alert_enabled_at IS NOT NULL AND alert_watermark_at IS NOT NULL)",
            name="ck_saved_job_searches_alert_activation",
        ),
        Index("idx_saved_job_searches_owner_updated", "user_id", "updated_at", "id"),
        Index(
            "idx_saved_job_searches_alert_activation",
            "alert_mode",
            "alert_watermark_at",
            "id",
        ),
    )


class JobAlert(Base):
    """One durable, private new-canonical-job alert per saved search."""

    __tablename__ = "job_alerts"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    saved_search_id = Column(
        UUID(as_uuid=True),
        ForeignKey("saved_job_searches.id", ondelete="CASCADE"),
        nullable=False,
    )
    canonical_job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("normalized_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Snapshot the delivery preference so later search changes cannot reinterpret
    # a queued event.
    delivery_mode = Column(String(20), nullable=False)
    delivery_state = Column(
        String(20),
        nullable=False,
        default=JobAlertDeliveryState.PENDING,
        server_default=text("'PENDING'"),
    )
    scheduled_for = Column(DateTime(timezone=True), nullable=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    last_error_code = Column(String(50), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "saved_search_id",
            "canonical_job_id",
            name="uq_job_alerts_owner_search_job",
        ),
        CheckConstraint(
            "delivery_mode IN ('INSTANT', 'HOURLY_DIGEST', 'DAILY_DIGEST')",
            name="ck_job_alerts_delivery_mode",
        ),
        CheckConstraint(
            "delivery_state IN ('PENDING', 'DELIVERED', 'FAILED', 'SUPPRESSED')",
            name="ck_job_alerts_delivery_state",
        ),
        CheckConstraint(
            "attempt_count BETWEEN 0 AND 3",
            name="ck_job_alerts_attempt_count",
        ),
        CheckConstraint(
            "last_error_code IS NULL OR last_error_code !~ '[[:cntrl:]]'",
            name="ck_job_alerts_error_safe",
        ),
        Index(
            "idx_job_alerts_owner_delivered_read",
            "user_id",
            "delivered_at",
            "read_at",
            "id",
        ),
        Index(
            "idx_job_alerts_due_delivery",
            "delivery_state",
            "scheduled_for",
            "next_retry_at",
            "id",
        ),
        Index("idx_job_alerts_canonical_job", "canonical_job_id", "id"),
    )


class JobSourceObservation(Base):
    """Current normalized facts and freshness for one source identity.

    Raw snapshots retain the immutable source payload history. This row keeps
    only the latest normalized source projection required for conservative
    canonical resolution and lifecycle decisions.
    """

    __tablename__ = "job_source_observations"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    canonical_job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("normalized_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_source_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("job_source_records.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    source_authority = Column(
        String(30),
        nullable=False,
        default=JobSourceAuthority.TRUSTED_STRUCTURED,
        server_default=text("'TRUSTED_STRUCTURED'"),
    )
    source_url = Column(String(1000), nullable=False)
    application_url = Column(String(1000), nullable=False)
    source_url_fingerprint = Column(CHAR(64), nullable=False)
    application_url_fingerprint = Column(CHAR(64), nullable=False)
    company_title_location_fingerprint = Column(CHAR(64), nullable=True)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role_id = Column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    employment_type = Column(String(50), nullable=False)
    career_level = Column(
        String(50), nullable=False, default="UNSPECIFIED", server_default=text("'UNSPECIFIED'")
    )
    work_mode = Column(
        String(30), nullable=False, default="UNSPECIFIED", server_default=text("'UNSPECIFIED'")
    )
    posted_at = Column(DateTime(timezone=True), nullable=True)
    source_updated_at = Column(DateTime(timezone=True), nullable=True)
    # New observations carry only normalized requirement/location facts. Older
    # records remain NULL until their source is successfully observed again.
    fact_projection = Column(JSONB, nullable=True)
    current_payload_hash_sha256 = Column(CHAR(64), nullable=True)
    first_seen_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    last_seen_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    last_verified_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    consecutive_absent_successes = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    last_absent_at = Column(DateTime(timezone=True), nullable=True)
    explicitly_closed = Column(
        Boolean, nullable=False, default=False, server_default=text("FALSE")
    )
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint(
            "source_authority IN "
            "('OFFICIAL_COMPANY', 'OFFICIAL_ATS', 'TRUSTED_STRUCTURED', "
            "'TRUSTED_AGGREGATOR', 'UNKNOWN')",
            name="ck_job_source_observation_authority",
        ),
        CheckConstraint(
            "source_url ~* '^https?://[^[:space:]]+$' "
            "AND application_url ~* '^https?://[^[:space:]]+$'",
            name="ck_job_source_observation_urls",
        ),
        CheckConstraint(
            "source_url_fingerprint ~ '^[0-9a-f]{64}$' "
            "AND application_url_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_job_source_observation_url_fingerprints",
        ),
        CheckConstraint(
            "company_title_location_fingerprint IS NULL OR "
            "company_title_location_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_job_source_observation_exact_fingerprint",
        ),
        CheckConstraint(
            "current_payload_hash_sha256 IS NULL OR "
            "current_payload_hash_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_job_source_observation_current_hash",
        ),
        CheckConstraint(
            "consecutive_absent_successes >= 0",
            name="ck_job_source_observation_absence_count",
        ),
        Index(
            "idx_job_source_observations_canonical",
            "canonical_job_id",
            "explicitly_closed",
            "consecutive_absent_successes",
        ),
        Index(
            "idx_job_source_observations_application_fingerprint",
            "application_url_fingerprint",
        ),
        Index(
            "idx_job_source_observations_source_fingerprint",
            "source_url_fingerprint",
        ),
        Index(
            "idx_job_source_observations_exact_fingerprint",
            "company_title_location_fingerprint",
        ),
    )


class JobIndustry(Base):
    __tablename__ = "job_industries"

    job_id = Column(
        UUID(as_uuid=True), ForeignKey("normalized_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    industry_id = Column(
        UUID(as_uuid=True),
        ForeignKey("industries.id", ondelete="CASCADE"),
        primary_key=True,
    )

    __table_args__ = (Index("idx_job_industries_industry", "industry_id"),)


class JobLocation(Base):
    __tablename__ = "job_locations"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("normalized_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id = Column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )
    location_raw = Column(String(255), nullable=False)

    __table_args__ = (Index("idx_job_locations_job", "job_id"),)


class JobSkillRequirement(Base):
    __tablename__ = "job_skill_requirements"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    job_id = Column(
        UUID(as_uuid=True), ForeignKey("normalized_jobs.id", ondelete="CASCADE"), nullable=False
    )
    skill_id = Column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    importance = Column(String(30), nullable=False)
    description = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("job_id", "skill_id", name="uq_job_skill_req"),
        Index("idx_job_skill_reqs_lookup", "skill_id", "job_id"),
    )


class JobEducationRequirement(Base):
    __tablename__ = "job_education_requirements"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("normalized_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    degree_level = Column(String(50), nullable=False)
    target_grad_start = Column(Date, nullable=True)
    target_grad_end = Column(Date, nullable=True)

    __table_args__ = (Index("idx_job_education_reqs_job", "job_id"),)


class JobEligibilityRequirement(Base):
    __tablename__ = "job_eligibility_requirements"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("normalized_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    requirement_type = Column(String(50), nullable=False)
    value = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    source_evidence = Column(Text, nullable=True)

    __table_args__ = (Index("idx_job_eligibility_reqs_job", "job_id"),)


__all__ = [
    "LiveSourceHealth",
    "LiveSourceState",
    "JobLifecycle",
    "JobSourceAuthority",
    "JobSourceRecord",
    "RawJobSnapshot",
    "NormalizedJob",
    "JobSourceObservation",
    "JobIndustry",
    "JobLocation",
    "JobSkillRequirement",
    "JobEducationRequirement",
    "JobEligibilityRequirement",
]
