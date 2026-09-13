"""Shared lease and heartbeat behavior for the production background workers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from backend.app.core.config import settings
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.models.operations import WorkerHeartbeat, WorkerRuntimeState
from backend.app.repositories.worker_heartbeat import WorkerHeartbeatRepository


@dataclass(frozen=True)
class WorkerHealth:
    worker_name: str
    status: str
    last_heartbeat_at: datetime | None
    last_completed_at: datetime | None


class WorkerRuntime:
    """Acquire one durable worker lease and refresh its heartbeat safely."""

    def __init__(
        self,
        worker_name: str,
        *,
        uow_factory=UnitOfWork,
        now=None,
        lease_seconds: int | None = None,
        token: UUID | None = None,
    ) -> None:
        if worker_name not in {"collector", "alert-worker"}:
            raise ValueError("Unknown production worker")
        self.worker_name = worker_name
        self._uow_factory = uow_factory
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.lease_seconds = lease_seconds or settings.WORKER_LEASE_SECONDS
        self.token = token or uuid4()
        self._owns_lease = False

    def claim(self) -> bool:
        now = self._utc_now()
        with self._uow_factory() as uow:
            repository = WorkerHeartbeatRepository(uow.session)
            self._owns_lease = repository.claim(
                self.worker_name,
                self.token,
                now,
                lease_seconds=self.lease_seconds,
            )
            uow.commit()
        return self._owns_lease

    def heartbeat(self, *, completed: bool = False) -> bool:
        if not self._owns_lease:
            return False
        now = self._utc_now()
        with self._uow_factory() as uow:
            repository = WorkerHeartbeatRepository(uow.session)
            self._owns_lease = repository.heartbeat(
                self.worker_name,
                self.token,
                now,
                lease_seconds=self.lease_seconds,
                completed=completed,
            )
            uow.commit()
        return self._owns_lease

    def release(self) -> bool:
        if not self._owns_lease:
            return False
        now = self._utc_now()
        with self._uow_factory() as uow:
            repository = WorkerHeartbeatRepository(uow.session)
            released = repository.release(self.worker_name, self.token, now)
            uow.commit()
        self._owns_lease = False
        return released

    @property
    def owns_lease(self) -> bool:
        return self._owns_lease

    def _utc_now(self) -> datetime:
        now = self._now()
        if now.tzinfo is None:
            raise ValueError("worker clock must return an aware timestamp")
        return now.astimezone(timezone.utc)


def worker_health(
    worker_name: str,
    *,
    session,
    now: datetime | None = None,
    stale_seconds: int | None = None,
) -> WorkerHealth:
    """Classify the last durable heartbeat without exposing process internals."""

    if worker_name not in {"collector", "alert-worker"}:
        raise ValueError("Unknown production worker")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stale_after = stale_seconds or settings.WORKER_HEARTBEAT_STALE_SECONDS
    row: WorkerHeartbeat | None = WorkerHeartbeatRepository(session).get(worker_name)
    if row is None:
        return WorkerHealth(worker_name, "not_started", None, None)
    if row.worker_state != WorkerRuntimeState.RUNNING:
        return WorkerHealth(worker_name, "stopped", row.last_heartbeat_at, row.last_completed_at)
    if (
        row.last_heartbeat_at is None
        or row.last_heartbeat_at < now - timedelta(seconds=stale_after)
        or row.lease_expires_at is None
        or row.lease_expires_at <= now
    ):
        return WorkerHealth(worker_name, "stale", row.last_heartbeat_at, row.last_completed_at)
    return WorkerHealth(worker_name, "healthy", row.last_heartbeat_at, row.last_completed_at)


__all__ = ["WorkerHealth", "WorkerRuntime", "worker_health"]
