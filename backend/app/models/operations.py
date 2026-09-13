"""Durable worker liveness and lease state for production operations."""

from sqlalchemy import CheckConstraint, Column, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import UUID

from backend.app.models.base import Base, utc_now


class WorkerRuntimeState:
    """Small explicit states for the singleton collector and alert worker."""

    RUNNING = "RUNNING"
    STOPPED = "STOPPED"


class WorkerHeartbeat(Base):
    """One durable logical-worker record, independent of source health.

    A renewable lease protects deployment overlap. A token means an older
    process cannot accidentally overwrite the heartbeat of its replacement.
    """

    __tablename__ = "worker_heartbeats"

    worker_name = Column(String(32), primary_key=True)
    worker_state = Column(
        String(12),
        nullable=False,
        default=WorkerRuntimeState.STOPPED,
        server_default=text("'STOPPED'"),
    )
    lease_token = Column(UUID(as_uuid=True), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    last_completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint(
            "worker_name IN ('collector', 'alert-worker')",
            name="ck_worker_heartbeat_name",
        ),
        CheckConstraint(
            "worker_state IN ('RUNNING', 'STOPPED')",
            name="ck_worker_heartbeat_state",
        ),
        Index("idx_worker_heartbeats_lease", "lease_expires_at"),
    )


__all__ = ["WorkerHeartbeat", "WorkerRuntimeState"]
