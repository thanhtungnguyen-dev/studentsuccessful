"""Focused production reliability checks for Phase 25."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import backend.app.api.health as health_api
from backend.app.core.logging import JsonFormatter
from backend.app.main import app
from backend.app.services.worker_runtime import WorkerRuntime, worker_health

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def test_worker_lease_blocks_overlap_then_recovers_after_expiry(isolated_database):
    clock = Clock()
    first = WorkerRuntime("collector", now=clock, lease_seconds=60)
    second = WorkerRuntime("collector", now=clock, lease_seconds=60)

    assert first.claim() is True
    assert second.claim() is False
    with sessionmaker(bind=isolated_database)() as session:
        assert worker_health("collector", session=session, now=clock(), stale_seconds=60).status == "healthy"

    clock.advance(61)
    assert second.claim() is True
    assert first.heartbeat(completed=True) is False
    assert second.heartbeat(completed=True) is True
    with sessionmaker(bind=isolated_database)() as session:
        state = worker_health("collector", session=session, now=clock(), stale_seconds=60)
    assert state.status == "healthy"
    assert state.last_completed_at == clock()


def test_worker_health_endpoint_only_exposes_aggregate_freshness(isolated_database, monkeypatch):
    clock = Clock(datetime.now(timezone.utc))
    collector = WorkerRuntime("collector", now=clock, lease_seconds=60)
    alerts = WorkerRuntime("alert-worker", now=clock, lease_seconds=60)
    assert collector.claim() and collector.heartbeat(completed=True)
    assert alerts.claim() and alerts.heartbeat(completed=True)

    factory = sessionmaker(bind=isolated_database)
    monkeypatch.setattr(health_api, "SessionLocal", factory)
    response = TestClient(app).get("/health/workers")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert {name: value["status"] for name, value in response.json()["workers"].items()} == {
        "collector": "healthy",
        "alert-worker": "healthy",
    }
    assert "lease" not in response.text.lower()


def test_readiness_fails_safely_when_required_dependencies_are_unavailable(monkeypatch):
    class DownSession:
        def __init__(self):
            raise RuntimeError("database unavailable")

    class DownStorage:
        def health_check(self):
            return False

    monkeypatch.setattr(health_api, "SessionLocal", DownSession)
    monkeypatch.setattr(health_api, "get_storage_adapter", lambda: DownStorage())

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["dependencies"] == {"database": False, "storage": False}


def test_request_id_security_headers_and_structured_logs_exclude_unapproved_fields():
    request_id = "phase25-request-id"
    response = TestClient(app).get("/health/live", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == request_id
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]

    record = logging.makeLogRecord(
        {
            "name": "studentsuccessful.test",
            "levelno": logging.INFO,
            "levelname": "INFO",
            "msg": "safe event",
            "args": (),
            "event": "safe_event",
            "password": "do-not-log-me",
            "csrf_token": "do-not-log-me",
        }
    )
    rendered = JsonFormatter().format(record)
    assert "safe_event" in rendered
    assert "do-not-log-me" not in rendered
