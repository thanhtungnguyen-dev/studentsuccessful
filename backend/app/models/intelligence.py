"""Source registry, discovery work and replay evidence alongside the existing collector."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.app.models.base import Base


class SourceRegistry(Base):
    __tablename__ = "source_registry"
    source_key = Column(String(50), primary_key=True)
    provider = Column(String(20), nullable=False)
    identity = Column(String(1000), nullable=False)
    configuration = Column(JSONB, nullable=False)
    origin = Column(String(12), nullable=False)
    enabled = Column(Boolean, nullable=False, server_default=text("true"))
    discovered_from = Column(String(1000))
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    __table_args__ = (
        UniqueConstraint("provider", "identity", name="uq_source_registry_identity"),
        CheckConstraint("origin IN ('CONFIGURED', 'DISCOVERED')", name="ck_source_registry_origin"),
    )


class SourceDiscoveryWork(Base):
    __tablename__ = "source_discovery_work"
    url_hash = Column(String(64), primary_key=True)
    url = Column(String(1000), nullable=False)
    company = Column(String(150), nullable=False)
    parent_source = Column(String(50), nullable=False)
    state = Column(String(20), nullable=False, server_default=text("'PENDING'"))
    attempts = Column(Integer, nullable=False, server_default=text("0"))
    due_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    result_source = Column(String(50))
    __table_args__ = (
        Index("idx_discovery_due", "state", "due_at"),
        CheckConstraint(
            "state IN ('PENDING', 'VERIFIED', 'UNKNOWN', 'FAILED')", name="ck_discovery_state"
        ),
        CheckConstraint("attempts BETWEEN 0 AND 3", name="ck_discovery_attempts"),
    )


class SourceFetchEvidence(Base):
    __tablename__ = "source_fetch_evidence"
    source_key = Column(String(50), primary_key=True)
    content_hash = Column(String(64), primary_key=True)
    parser_version = Column(String(20), nullable=False)
    configuration = Column(JSONB, nullable=False)
    pages = Column(JSONB, nullable=False)
    first_fetched_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    last_fetched_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class JobChangeEvent(Base):
    __tablename__ = "job_change_events"
    event_key = Column(String(64), primary_key=True)
    job_id = Column(
        UUID(as_uuid=True), ForeignKey("normalized_jobs.id", ondelete="CASCADE"), nullable=False
    )
    observation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("job_source_observations.id", ondelete="CASCADE"),
        nullable=False,
    )
    previous_hash = Column(String(64))
    current_hash = Column(String(64), nullable=False)
    changed_fields = Column(JSONB, nullable=False)
    observed_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    __table_args__ = (Index("idx_job_changes_job_time", "job_id", "observed_at"),)
