"""PostgreSQL employment facts, ownership, merged edits and row concurrency."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.main import app
from backend.app.models.profile import ApplicationProfile, EmploymentRecord
from backend.app.models.user import User
from backend.app.schemas.employment import EmploymentCreate, EmploymentUpdate
from backend.app.services.employment import EmploymentService

URL = "/api/v1/profile/employment"
FACTS = dict(employer_name="Example Employer", job_title="Developer", start_date="2026-01-01", currently_employed=True)


def register():
    client = TestClient(app)
    result = client.post("/api/v1/auth/register", json={"email": f"employment-{uuid4().hex}@example.com", "password": "Employment-password-123!"})
    assert result.status_code == 201
    return client, UUID(result.json()["user"]["id"])


def mutate(client, method, payload=None, id=None):
    return client.request(method, URL + (f"/{id}" if id else ""), json=payload,
                          headers={"X-CSRF-Token": client.cookies["ss_csrf"]})


def create(client, **extra):
    result = mutate(client, "POST", {**FACTS, **extra})
    assert result.status_code == 201, result.text
    assert result.headers["cache-control"] == "no-store"
    assert "user_id" not in result.json()
    return result.json()


def test_create_list_owner_no_profile_and_text_preservation():
    client, owner = register()
    assert client.get(URL).json() == []
    first = create(client, employer_name="  Société 李  ", job_title="  Développeur  ", location="  Calgary, Alberta  ", description="  Exact text\n  second line <b>facts</b>  ")
    assert first["employer_name"] == "Société 李"
    assert first["job_title"] == "Développeur"
    assert first["location"] == "Calgary, Alberta"
    assert first["description"] == "  Exact text\n  second line <b>facts</b>  "
    assert first["end_date"] is None
    assert client.get(URL).json() == [first]
    second = create(client, employer_name="Second")
    result = client.get(URL)
    assert result.headers["cache-control"] == "no-store"
    assert result.json() == sorted([first, second], key=lambda row: (row["created_at"], row["id"]))
    assert client.get(URL).json() == result.json()
    with UnitOfWork() as uow:
        assert uow.session.get(EmploymentRecord, UUID(first["id"])).user_id == owner
        assert uow.session.scalar(select(ApplicationProfile).where(ApplicationProfile.user_id == owner)) is None


@pytest.mark.parametrize("current,end", [(True, None), (True, "2027-05-01"), (False, "2026-08-31"), (False, "2026-01-01")])
def test_accepted_current_and_end_date_semantics(current, end):
    client, _ = register()
    row = create(client, currently_employed=current, end_date=end)
    assert row["currently_employed"] is current and row["end_date"] == end


def test_default_false_with_complete_end_date():
    client, _ = register()
    response = mutate(client, "POST", {key: value for key, value in {**FACTS, "end_date": "2026-08-31"}.items() if key != "currently_employed"})
    assert response.status_code == 201 and response.json()["currently_employed"] is False


@pytest.mark.parametrize("method,id", [("GET", None), ("POST", None), ("PATCH", str(uuid4())), ("DELETE", str(uuid4()))])
def test_unauthenticated_rejected(method, id):
    assert TestClient(app).request(method, URL + (f"/{id}" if id else ""), json=FACTS if method in {"POST", "PATCH"} else None).status_code == 401


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
def test_csrf_required_for_all_mutations(method):
    client, _ = register()
    other, _ = register()
    row = create(client)
    path = URL if method == "POST" else f"{URL}/{row['id']}"
    for token in (None, "wrong", other.cookies["ss_csrf"]):
        response = client.request(method, path, json=FACTS if method != "DELETE" else None, headers={} if token is None else {"X-CSRF-Token": token})
        assert response.status_code == 403
    assert client.get(URL).json() == [row]
    assert mutate(client, method, FACTS if method != "DELETE" else None, None if method == "POST" else row["id"]).status_code == {"POST": 201, "PATCH": 200, "DELETE": 204}[method]


def test_idor_and_injected_ownership():
    client, owner = register()
    other, _ = register()
    row = create(client)
    assert other.get(URL).json() == []
    assert other.get(f"{URL}?user_id={owner}").status_code == 422
    assert mutate(other, "POST", {**FACTS, "user_id": str(owner)}).status_code == 422
    assert mutate(client, "PATCH", {"user_id": str(uuid4())}, row["id"]).status_code == 422
    for method in ("PATCH", "DELETE"):
        responses = [mutate(other, method, {"job_title": "Changed"} if method == "PATCH" else None, id) for id in (row["id"], str(uuid4()))]
        assert all(response.status_code == 404 for response in responses)
        assert responses[0].json()["code"] == responses[1].json()["code"] == "EMPLOYMENT_NOT_FOUND"
        assert responses[0].json()["detail"] == responses[1].json()["detail"]
    assert client.get(URL).json() == [row]


@pytest.mark.parametrize("key,new", [("employer_name", "New employer"), ("job_title", "New title")])
def test_single_field_patch_preserves_all_other_values(key, new):
    client, _ = register()
    row = create(client, location="Calgary", description="Notes", end_date="2027-05-01")
    response = mutate(client, "PATCH", {key: new}, row["id"])
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    for field in row.keys() - {key, "updated_at"}:
        assert response.json()[field] == row[field]
    assert response.json()[key] == new


@pytest.mark.parametrize("key", ["location", "description"])
@pytest.mark.parametrize("value", [None, " \n "])
def test_optional_fields_clear(key, value):
    client, _ = register()
    row = create(client, location="Calgary", description="Notes")
    response = mutate(client, "PATCH", {key: value}, row["id"])
    assert response.status_code == 200 and response.json()[key] is None
    assert client.get(URL).json()[0][key] is None


@pytest.mark.parametrize("payload", [
    {"currently_employed": False}, {"end_date": "2025-12-31"}, {"employer_name": " "},
    {"job_title": " "}, {"employer_name": "x" * 256}, {"job_title": "x" * 151}, {"location": "x" * 151},
    {"employer_name": None}, {"job_title": None}, {"start_date": None}, {"currently_employed": None},
    {"start_date": "not-date"}, {"description": ["not text"]}, {"employment_type": "FULL_TIME"}, {"skills": ["Python"]},
])
def test_invalid_create_and_patch_leave_facts_unchanged(payload):
    client, _ = register()
    assert mutate(client, "POST", {**FACTS, **payload}).status_code == 422
    assert client.get(URL).json() == []
    row = create(client)
    assert mutate(client, "PATCH", payload, row["id"]).status_code == 422
    assert client.get(URL).json() == [row]


def test_final_state_transitions_and_order():
    client, _ = register()
    row = create(client)
    assert mutate(client, "PATCH", {"currently_employed": False}, row["id"]).status_code == 422
    completed = mutate(client, "PATCH", {"currently_employed": False, "end_date": "2026-08-31"}, row["id"]).json()
    for payload in ({"end_date": None}, {"start_date": "2026-09-01"}, {"end_date": "2025-12-31"}):
        assert mutate(client, "PATCH", {**payload, "job_title": "Must not persist"}, row["id"]).status_code == 422
        assert client.get(URL).json() == [completed]
    current = mutate(client, "PATCH", {"currently_employed": True}, row["id"])
    assert current.status_code == 200 and current.json()["end_date"] == "2026-08-31"
    assert mutate(client, "PATCH", {"end_date": None}, row["id"]).status_code == 200


def test_delete_only_owned_selected_record():
    client, _ = register()
    first = create(client)
    second = create(client, employer_name="Second")
    response = mutate(client, "DELETE", id=first["id"])
    assert response.status_code == 204 and response.content == b""
    assert response.headers["cache-control"] == "no-store"
    assert client.get(URL).json() == [second]
    assert mutate(client, "DELETE", id=first["id"]).status_code == 404


def test_independent_commit_and_concurrent_merged_edits(database_engine):
    factory = sessionmaker(bind=database_engine)
    owner = uuid4()
    try:
        with factory.begin() as session:
            session.add(User(id=owner, email=f"employment-commit-{owner}@example.com", password_hash="test"))
        with UnitOfWork(factory) as uow:
            row = EmploymentService.create(owner, EmploymentCreate(**{**FACTS, "end_date": "2026-12-31"}), uow)
        with factory() as session:
            assert session.get(EmploymentRecord, row.id).employer_name == FACTS["employer_name"]
        with UnitOfWork(factory) as uow:
            EmploymentService.update(owner, row.id, EmploymentUpdate(job_title="Committed"), uow)
        with factory() as session:
            assert session.get(EmploymentRecord, row.id).job_title == "Committed"
        barrier = Barrier(2)

        def change(payload):
            barrier.wait(timeout=10)
            try:
                with UnitOfWork(factory) as uow:
                    EmploymentService.update(owner, row.id, EmploymentUpdate(**payload), uow)
                return "saved"
            except ValidationError:
                return "invalid_final_state"

        # Each fragment is valid against the original; the combination is invalid.
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(change, payload) for payload in ({"start_date": "2026-11-01"}, {"end_date": "2026-02-01"})]
            assert sorted(future.result(timeout=20) for future in futures) == ["invalid_final_state", "saved"]
        with factory() as session:
            stored = session.get(EmploymentRecord, row.id)
            assert stored.end_date >= stored.start_date
        with UnitOfWork(factory) as uow:
            EmploymentService.delete(owner, row.id, uow)
        with factory() as session:
            assert session.get(EmploymentRecord, row.id) is None
    finally:
        with factory.begin() as session:
            session.execute(delete(User).where(User.id == owner))
