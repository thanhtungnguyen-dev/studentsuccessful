"""PostgreSQL authorization facts, isolation, timestamps and concurrent conflicts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.main import app
from backend.app.models.profile import ApplicationProfile, WorkAuthorization
from backend.app.models.user import User
from backend.app.schemas.work_authorization import (
    AuthorizationStatus,
    WorkAuthorizationCreate,
    WorkAuthorizationUpdate,
)
from backend.app.services.work_authorization import WorkAuthorizationService

URL = "/api/v1/profile/work-authorizations"
FACTS = dict(country_code="CA", authorization_status="OTHER", requires_current_sponsorship=True, requires_future_sponsorship=False)


def register():
    client = TestClient(app)
    result = client.post("/api/v1/auth/register", json={"email": f"wa-{uuid4().hex}@example.com", "password": "Authorization-password-123!"})
    assert result.status_code == 201
    return client, UUID(result.json()["user"]["id"])


def mutate(client, method, payload=None, id=None):
    return client.request(method, URL + (f"/{id}" if id else ""), json=payload, headers={"X-CSRF-Token": client.cookies["ss_csrf"]})


def create(client, **extra):
    result = mutate(client, "POST", {**FACTS, **extra})
    assert result.status_code == 201, result.text
    assert result.headers["cache-control"] == "no-store"
    assert "user_id" not in result.json()
    return result.json()


def test_create_list_normalization_owner_and_no_profile():
    client, owner = register()
    assert client.get(URL).json() == []
    before = datetime.now(timezone.utc)
    us = create(client, country_code=" us ", notes="  Exact <b>facts</b>  ")
    assert us["country_code"] == "US" and us["notes"] == "Exact <b>facts</b>"
    assert all(us[key].endswith("Z") for key in ("last_confirmed_at", "created_at", "updated_at"))
    assert before <= datetime.fromisoformat(us["last_confirmed_at"]) <= datetime.now(timezone.utc)
    assert client.get(URL).json() == [us]
    ca = create(client)
    assert client.get(URL).json() == [ca, us]
    assert client.get(URL).headers["cache-control"] == "no-store"
    with UnitOfWork() as uow:
        assert uow.session.get(WorkAuthorization, UUID(ca["id"])).user_id == owner
        assert uow.session.scalar(select(ApplicationProfile).where(ApplicationProfile.user_id == owner)) is None


@pytest.mark.parametrize("status", list(AuthorizationStatus))
def test_all_statuses_preserve_independent_sponsorship(status):
    client, _ = register()
    row = create(client, authorization_status=status, requires_current_sponsorship=True, requires_future_sponsorship=False)
    assert row["authorization_status"] == status
    assert row["requires_current_sponsorship"] is True and row["requires_future_sponsorship"] is False
    result = mutate(client, "PATCH", {"requires_current_sponsorship": False, "requires_future_sponsorship": True}, row["id"])
    assert result.status_code == 200
    assert result.json()["authorization_status"] == status
    assert result.json()["requires_current_sponsorship"] is False and result.json()["requires_future_sponsorship"] is True


@pytest.mark.parametrize("method,id", [("GET", None), ("POST", None), ("PATCH", str(uuid4())), ("DELETE", str(uuid4()))])
def test_unauthenticated(method, id):
    assert TestClient(app).request(method, URL + (f"/{id}" if id else ""), json=FACTS if method in {"POST", "PATCH"} else None).status_code == 401


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
def test_csrf(method):
    client, _ = register()
    other, _ = register()
    row = create(client)
    path = URL if method == "POST" else f"{URL}/{row['id']}"
    for token in (None, "wrong", other.cookies["ss_csrf"]):
        response = client.request(method, path, json={**FACTS, "country_code": "US"} if method != "DELETE" else None, headers={} if token is None else {"X-CSRF-Token": token})
        assert response.status_code == 403
    assert client.get(URL).json() == [row]
    assert mutate(client, method, {**FACTS, "country_code": "US"} if method != "DELETE" else None, None if method == "POST" else row["id"]).status_code == {"POST": 201, "PATCH": 200, "DELETE": 204}[method]


def test_idor_and_owner_injection():
    client, owner = register()
    other, _ = register()
    row = create(client)
    assert other.get(URL).json() == []
    for method in ("GET", "POST", "PATCH", "DELETE"):
        path = URL + (f"/{row['id']}" if method in {"PATCH", "DELETE"} else "") + f"?user_id={owner}"
        assert client.request(method, path, json=FACTS if method in {"POST", "PATCH"} else None, headers={"X-CSRF-Token": client.cookies["ss_csrf"]}).status_code == 422
    assert mutate(other, "POST", {**FACTS, "user_id": str(owner)}).status_code == 422
    assert mutate(client, "PATCH", {"user_id": str(uuid4())}, row["id"]).status_code == 422
    for method in ("PATCH", "DELETE"):
        responses = [mutate(other, method, {"notes": "Changed"} if method == "PATCH" else None, id) for id in (row["id"], str(uuid4()))]
        assert all(response.status_code == 404 for response in responses)
        assert responses[0].json()["code"] == responses[1].json()["code"] == "WORK_AUTHORIZATION_NOT_FOUND"
        assert responses[0].json()["detail"] == responses[1].json()["detail"]
    assert client.get(URL).json() == [row]


@pytest.mark.parametrize("changes", [
    {"country_code": "C"}, {"country_code": "CAN"}, {"country_code": "1A"}, {"country_code": "éA"}, {"country_code": "ß"},
    {"country_code": None}, {"authorization_status": "UNKNOWN"}, {"authorization_status": None},
    {"requires_current_sponsorship": None}, {"requires_future_sponsorship": None},
    {"requires_current_sponsorship": "false"}, {"requires_future_sponsorship": 1},
    {"notes": "x" * 256}, {"last_confirmed_at": "2000-01-01T00:00:00Z"}, {"id": str(uuid4())},
    {"created_at": "2000-01-01T00:00:00Z"}, {"updated_at": "2000-01-01T00:00:00Z"}, {"nationality": "CA"}
])
def test_invalid_create_and_patch_leave_facts_unchanged(changes):
    client, _ = register()
    row = create(client)
    assert mutate(client, "POST", {**FACTS, **changes}).status_code == 422
    assert mutate(client, "PATCH", changes, row["id"]).status_code == 422
    assert client.get(URL).json() == [row]


@pytest.mark.parametrize("key,value", [("requires_future_sponsorship", True), ("authorization_status", "CITIZEN"), ("notes", None), ("notes", "   "), ("country_code", "gb")])
def test_partial_updates_confirmation_and_get_empty_patch(key, value):
    client, _ = register()
    row = create(client, notes="Keep unless explicitly cleared")
    assert client.get(URL).json() == [row]
    assert mutate(client, "PATCH", {}, row["id"]).json() == row
    response = mutate(client, "PATCH", {key: value}, row["id"])
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    updated = response.json()
    for field in row.keys() - {key, "last_confirmed_at", "updated_at"}:
        assert updated[field] == row[field]
    expected = "GB" if key == "country_code" else None if key == "notes" else value
    assert updated[key] == expected
    assert datetime.fromisoformat(updated["last_confirmed_at"]) > datetime.fromisoformat(row["last_confirmed_at"])
    assert client.get(URL).json() == [updated]
    # Explicitly resubmitting an unchanged fact still confirms it.
    again = mutate(client, "PATCH", {key: expected}, row["id"]).json()
    assert datetime.fromisoformat(again["last_confirmed_at"]) > datetime.fromisoformat(updated["last_confirmed_at"])


def test_duplicate_post_and_country_patch_controlled_and_rollback():
    client, _ = register()
    other, _ = register()
    ca, us = create(client), create(client, country_code="US")
    create(other)
    for response in [mutate(client, "POST", {**FACTS, "country_code": "ca"}), mutate(client, "PATCH", {"country_code": "ca", "notes": "Must rollback"}, us["id"])]:
        assert response.status_code == 409 and response.json()["code"] == "WORK_AUTHORIZATION_ALREADY_EXISTS"
    assert client.get(URL).json() == [ca, us]


def test_delete_and_independent_persistence(database_engine, monkeypatch):
    from backend.app.core import unit_of_work

    factory = sessionmaker(bind=database_engine, expire_on_commit=False)
    monkeypatch.setattr(unit_of_work, "SessionLocal", factory)
    owner = None
    try:
        client, owner = register()
        row = create(client)
        keep = create(client, country_code="US")
        with UnitOfWork() as uow:
            assert uow.session.get(WorkAuthorization, UUID(row["id"])).country_code == "CA"
        response = mutate(client, "PATCH", {"notes": "Persist"}, row["id"])
        assert response.status_code == 200
        with UnitOfWork() as uow:
            assert uow.session.get(WorkAuthorization, UUID(row["id"])).notes == "Persist"
        response = mutate(client, "DELETE", id=row["id"])
        assert response.status_code == 204 and not response.content and response.headers["cache-control"] == "no-store"
        with UnitOfWork() as uow:
            assert uow.session.get(WorkAuthorization, UUID(row["id"])) is None
        assert client.get(URL).json() == [keep]
        assert mutate(client, "DELETE", id=row["id"]).status_code == 404
    finally:
        if owner is not None:
            with factory.begin() as session:
                session.execute(delete(User).where(User.id == owner))


@pytest.mark.parametrize("operation", ["POST", "PATCH"])
def test_concurrent_country_conflicts(database_engine, operation):
    factory = sessionmaker(bind=database_engine, expire_on_commit=False)
    owner = uuid4()
    with factory.begin() as session:
        session.add(User(id=owner, email=f"concurrent-wa-{owner}@example.com", password_hash="test"))
    try:
        ids = []
        if operation == "PATCH":
            for country in ("CA", "US"):
                with UnitOfWork(factory) as uow:
                    ids.append(WorkAuthorizationService.create(owner, WorkAuthorizationCreate(**{**FACTS, "country_code": country}), uow).id)
        barrier = Barrier(2)
        def writer(index):
            with UnitOfWork(factory) as uow:
                barrier.wait(timeout=10)
                try:
                    if operation == "POST":
                        WorkAuthorizationService.create(owner, WorkAuthorizationCreate(**FACTS), uow)
                    else:
                        WorkAuthorizationService.update(owner, ids[index], WorkAuthorizationUpdate(country_code="GB"), uow)
                    return "saved"
                except StudentSuccessfulException as error:
                    assert error.status_code == 409 and error.code == "WORK_AUTHORIZATION_ALREADY_EXISTS"
                    return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(writer, [0, 1])) == ["conflict", "saved"]
        with factory() as session:
            rows = list(session.scalars(select(WorkAuthorization).where(WorkAuthorization.user_id == owner)))
            assert len(rows) == (1 if operation == "POST" else 2)
            assert sum(row.country_code == ("CA" if operation == "POST" else "GB") for row in rows) == 1
    finally:
        with factory.begin() as session:
            session.execute(delete(User).where(User.id == owner))
