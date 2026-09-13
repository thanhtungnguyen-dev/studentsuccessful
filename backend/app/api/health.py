"""Health check endpoints reflecting system liveness and readiness."""

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from backend.app.core.database import SessionLocal
from backend.app.core.storage import get_storage_adapter
from backend.app.schemas.common import (
    HealthStatus,
    InfrastructureReadiness,
    ReadyStatus,
    WorkerHealthStatus,
    WorkerRuntimeHealth,
)
from backend.app.services.worker_runtime import worker_health

router = APIRouter(tags=["Health"])


@router.get("/health/live", response_model=HealthStatus)
def health_live():
    """Unversioned liveness endpoint confirming process execution."""
    return HealthStatus(status="ok")


@router.get("/health/ready", response_model=ReadyStatus)
def health_ready(response: Response):
    """
    Unversioned readiness endpoint verifying required infrastructure dependencies.
    - Database: required for all application persistence.
    - Storage: required for storing/retrieving uploaded resume documents.
    """
    db_ready = False
    session = None
    try:
        session = SessionLocal()
        session.execute(text("SELECT 1"))
        db_ready = True
    except Exception:
        db_ready = False
    finally:
        if session is not None:
            session.close()

    # Verify storage readiness using StorageAdapter
    storage_ready = False
    try:
        storage = get_storage_adapter()
        storage_ready = storage.health_check()
    except Exception:
        storage_ready = False

    is_all_ready = db_ready and storage_ready

    if not is_all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadyStatus(
        status="ready" if is_all_ready else "not_ready",
        dependencies=InfrastructureReadiness(
            database=db_ready,
            storage=storage_ready
        )
    )


@router.get("/health/workers", response_model=WorkerHealthStatus)
def health_workers(response: Response):
    """Expose only aggregate background-worker freshness for platform monitoring."""

    session = None
    statuses: dict[str, WorkerRuntimeHealth] = {}
    try:
        session = SessionLocal()
        for worker_name in ("collector", "alert-worker"):
            state = worker_health(worker_name, session=session)
            statuses[worker_name] = WorkerRuntimeHealth(
                status=state.status,
                last_heartbeat_at=state.last_heartbeat_at,
                last_completed_at=state.last_completed_at,
            )
    except Exception:
        statuses = {
            worker_name: WorkerRuntimeHealth(status="unavailable")
            for worker_name in ("collector", "alert-worker")
        }
    finally:
        if session is not None:
            session.close()

    healthy = all(state.status == "healthy" for state in statuses.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return WorkerHealthStatus(
        status="ok" if healthy else "degraded",
        workers=statuses,
    )
