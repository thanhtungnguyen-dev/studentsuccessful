"""Explicit completion, ownership and real PostgreSQL writer contention."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from backend.app.core import unit_of_work
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.main import app
from backend.app.models.base import Base
from backend.app.models.user import User
from backend.app.services.auth import AuthService

URL = "/api/v1/auth/onboarding/complete"


def register(client):
    response = client.post("/api/v1/auth/register", json={"email": f"onboard-{uuid4()}@example.com", "password": "Password123!"})
    assert response.status_code == 201
    return response.json()


def complete(client, auth, payload=None):
    return client.post(URL, json={} if payload is None else payload, headers={"X-CSRF-Token": auth["csrf_token"]})


def test_default_persistence_session_idempotence_and_single_commit(isolated_database):
    with TestClient(app) as client:
        auth = register(client)
        assert auth["user"]["onboarding_completed_at"] is None
        assert client.get("/api/v1/auth/me").json()["onboarding_completed_at"] is None
        user_id = UUID(auth["user"]["id"])
        before = dict(isolated_database.execute(select(User.__table__).where(User.id == user_id)).mappings().one())
        start = datetime.now(timezone.utc)
        original_commit = UnitOfWork.commit
        with patch.object(UnitOfWork, "commit", autospec=True, side_effect=original_commit) as commit:
            first = complete(client, auth)
            assert first.status_code == 200
            assert commit.call_count == 1
        timestamp = first.json()["onboarding_completed_at"]
        assert start <= datetime.fromisoformat(timestamp.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
        for _ in range(3):
            assert complete(client, auth).json() == first.json()
        assert client.get("/api/v1/auth/me").json() == first.json()
        after = dict(isolated_database.execute(select(User.__table__).where(User.id == user_id)).mappings().one())
        assert after.pop("onboarding_completed_at") is not None
        before.pop("onboarding_completed_at")
        assert before == after
        assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": auth["csrf_token"]}).status_code == 200
        login = client.post("/api/v1/auth/login", json={"email": auth["user"]["email"], "password": "Password123!"})
        assert login.json()["user"]["onboarding_completed_at"] == timestamp
        assert client.get("/api/v1/auth/me").json()["onboarding_completed_at"] == timestamp


def test_unauthorized_and_csrf_rejected():
    with TestClient(app) as client:
        assert client.post(URL, json={}).status_code == 401
        auth = register(client)
        assert client.post(URL, json={}).status_code == 403
        assert client.post(URL, json={}, headers={"X-CSRF-Token": "foreign"}).status_code == 403
        assert client.get("/api/v1/auth/me").json()["onboarding_completed_at"] is None
        assert complete(client, auth).status_code == 200


@pytest.mark.parametrize("field", ["user_id", "id", "onboarding_completed_at"])
def test_cannot_supply_another_user_or_timestamp(field):
    with TestClient(app) as owner, TestClient(app) as other:
        auth, victim = register(owner), register(other)
        value = victim["user"]["id"] if field != "onboarding_completed_at" else "2000-01-01T00:00:00Z"
        assert complete(owner, auth, {field: value}).status_code == 422
        assert other.get("/api/v1/auth/me").json()["onboarding_completed_at"] is None
        assert owner.get("/api/v1/auth/me").json()["onboarding_completed_at"] is None
        assert complete(owner, auth).status_code == 200
        assert other.get("/api/v1/auth/me").json()["onboarding_completed_at"] is None


def test_completion_preserves_all_saved_facts_and_preferences(isolated_database):
    with TestClient(app) as client:
        auth = register(client)
        headers = {"X-CSRF-Token": auth["csrf_token"]}
        writes = [
            ("PATCH", "/profile", {"legal_first_name": "Ada", "legal_last_name": "Lovelace"}, 200),
            ("POST", "/profile/education", {"institution_name": "Example University", "degree_level": "BS", "major": "Computing", "study_year": "YEAR_2", "start_date": "2025-01-01", "expected_grad_month": 5, "expected_grad_year": 2028, "is_primary": True}, 201),
            ("POST", "/profile/employment", {"employer_name": "Example Employer", "job_title": "Developer", "start_date": "2026-01-01", "currently_employed": True}, 201),
            ("POST", "/profile/work-authorizations", {"country_code": "CA", "authorization_status": "OTHER", "requires_current_sponsorship": False, "requires_future_sponsorship": True}, 201),
            ("PUT", "/preferences", {"work_modes": ["REMOTE"], "employment_types": ["CO_OP"], "custom_values": [{"preference_type": "SKILL", "value": "Rust interest"}]}, 200),
        ]
        for method, path, data, status in writes:
            response = client.request(method, "/api/v1" + path, json=data, headers=headers)
            assert response.status_code == status, response.text
        assert client.get("/api/v1/auth/me").json()["onboarding_completed_at"] is None
        def snapshot():
            return {table.name: list(isolated_database.execute(select(table)).mappings()) for table in Base.metadata.sorted_tables if table.name != "users"}
        before = snapshot()
        assert complete(client, auth).status_code == 200
        assert complete(client, auth).status_code == 200
        assert snapshot() == before


def test_concurrent_http_completions_use_one_timestamp(database_engine, monkeypatch):
    # Independent committed connections are essential: savepoint fixtures cannot prove contention.
    monkeypatch.setattr(unit_of_work, "SessionLocal", sessionmaker(bind=database_engine))
    with TestClient(app) as client:
        auth = register(client)
        user_id = UUID(auth["user"]["id"])
        cookie_values = dict(client.cookies)
        barrier = Barrier(2)
        operation = AuthService.complete_onboarding
        def synchronized(user, uow):
            assert user.onboarding_completed_at is None
            barrier.wait(timeout=10)
            return operation(user, uow)
        def request():
            with TestClient(app) as peer:
                peer.cookies.update(cookie_values)
                result = complete(peer, auth)
                assert result.status_code == 200, result.text
                return result.json()["onboarding_completed_at"]
        try:
            with patch.object(AuthService, "complete_onboarding", side_effect=synchronized), ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(request) for _ in range(2)]
                timestamps = [future.result(timeout=20) for future in futures]
            assert timestamps[0] is not None
            assert timestamps[0] == timestamps[1]
            assert complete(client, auth).json()["onboarding_completed_at"] == timestamps[0]
            with database_engine.connect() as connection:
                persisted = connection.execute(select(User.onboarding_completed_at).where(User.id == user_id)).scalar_one()
                assert persisted == datetime.fromisoformat(timestamps[0].replace("Z", "+00:00"))
        finally:
            with database_engine.begin() as connection:
                connection.execute(delete(User).where(User.id == user_id))
