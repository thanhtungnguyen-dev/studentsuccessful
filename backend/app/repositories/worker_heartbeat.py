"""Transactional storage for durable production worker leases and heartbeats."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from backend.app.models.operations import WorkerHeartbeat, WorkerRuntimeState


class WorkerHeartbeatRepository:
    """Owns row-level lease transitions; callers retain commit control."""

    def __init__(self, session) -> None:
        self.session = session

    def claim(
        self,
        worker_name: str,
        token: UUID,
        now: datetime,
        *,
        lease_seconds: int,
    ) -> bool:
        # Concurrent first starts must serialize on the existing singleton row.
        self.session.execute(
            insert(WorkerHeartbeat).values(worker_name=worker_name).on_conflict_do_nothing(
                index_elements=["worker_name"]
            )
        )
        row = self._locked(worker_name)
        if row is not None and self._held_by_another(row, token, now):
            return False
        if row is None:
            row = WorkerHeartbeat(worker_name=worker_name)
            self.session.add(row)
        row.worker_state = WorkerRuntimeState.RUNNING
        row.lease_token = token
        row.lease_expires_at = now + timedelta(seconds=lease_seconds)
        row.started_at = now
        row.last_heartbeat_at = now
        row.updated_at = now
        self.session.flush()
        return True

    def heartbeat(
        self,
        worker_name: str,
        token: UUID,
        now: datetime,
        *,
        lease_seconds: int,
        completed: bool,
    ) -> bool:
        row = self._locked(worker_name)
        if row is None or row.lease_token != token or row.worker_state != WorkerRuntimeState.RUNNING:
            return False
        row.lease_expires_at = now + timedelta(seconds=lease_seconds)
        row.last_heartbeat_at = now
        if completed:
            row.last_completed_at = now
        row.updated_at = now
        self.session.flush()
        return True

    def release(self, worker_name: str, token: UUID, now: datetime) -> bool:
        row = self._locked(worker_name)
        if row is None or row.lease_token != token:
            return False
        row.worker_state = WorkerRuntimeState.STOPPED
        row.lease_expires_at = now
        row.last_heartbeat_at = now
        row.updated_at = now
        self.session.flush()
        return True

    def get(self, worker_name: str) -> WorkerHeartbeat | None:
        return self.session.get(WorkerHeartbeat, worker_name)

    def _locked(self, worker_name: str) -> WorkerHeartbeat | None:
        return self.session.scalar(
            select(WorkerHeartbeat)
            .where(WorkerHeartbeat.worker_name == worker_name)
            .with_for_update()
        )

    @staticmethod
    def _held_by_another(row: WorkerHeartbeat, token: UUID, now: datetime) -> bool:
        return (
            row.worker_state == WorkerRuntimeState.RUNNING
            and row.lease_token != token
            and row.lease_expires_at is not None
            and row.lease_expires_at > now
        )


__all__ = ["WorkerHeartbeatRepository"]
