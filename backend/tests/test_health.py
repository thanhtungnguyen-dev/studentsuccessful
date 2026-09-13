"""Tests for health check endpoints."""

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health_live():
    """Verify that /health/live returns HTTP 200 and status ok."""
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_health_ready():
    """Verify that /health/ready evaluates database and storage readiness."""
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["dependencies"]["database"] is True
    assert data["dependencies"]["storage"] is True
