"""Pydantic request and response schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthStatus(StrictBaseModel):
    status: str = Field(..., description="Liveness indicator, e.g., 'ok'")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class InfrastructureReadiness(StrictBaseModel):
    database: bool = Field(..., description="PostgreSQL connectivity state")
    storage: bool = Field(..., description="File storage availability state")


class ReadyStatus(StrictBaseModel):
    status: str = Field(..., description="'ready' or 'not_ready'")
    dependencies: InfrastructureReadiness
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WorkerRuntimeHealth(StrictBaseModel):
    status: str = Field(..., description="healthy, stale, stopped, or not_started")
    last_heartbeat_at: datetime | None = None
    last_completed_at: datetime | None = None


class WorkerHealthStatus(StrictBaseModel):
    status: str = Field(..., description="ok when every required worker is healthy")
    workers: dict[str, WorkerRuntimeHealth]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ProblemDetail(StrictBaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str | None = None
    code: str
    errors: list[dict[str, Any]] | None = None
