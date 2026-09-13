"""Education API integration: explicit facts, merged PATCH and owner isolation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.main import app
from backend.app.models.profile import ApplicationProfile, EducationRecord
from backend.app.models.user import User
from backend.app.schemas.education import EducationCreate, EducationUpdate
from backend.app.services.education import EducationService

URL = "/api/v1/profile/education"
FACTS = dict(institution_name="University of Calgary", degree_level="BS", major="Computer Science",
             study_year="YEAR_3", start_date="2024-09-01", expected_grad_month=6, expected_grad_year=2028)


def register():
    client = TestClient(app)
    result = client.post("/api/v1/auth/register", json={"email": f"education-{uuid4().hex}@example.com", "password": "Education-password-123!"})
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


def test_create_list_without_application_profile_and_no_inference():
    client, owner = register()
    assert client.get(URL).json() == []
    first = create(client, institution_name="  École 李  ", major="  Mathématiques  ", minor="  Art  ")
    assert first["institution_name"] == "École 李"
    assert first["major"] == "Mathématiques"
    assert first["minor"] == "Art"
    assert first["gpa_value"] is None and first["gpa_scale"] is None
    assert first["gpa_include_on_apps"] is False and first["is_primary"] is False
    assert client.get(URL).json() == [first]
    second = create(client, institution_name="Second", degree_level="OTHER", study_year="OTHER")
    records = client.get(URL)
    assert records.headers["cache-control"] == "no-store"
    assert records.json() == sorted([first, second], key=lambda item: (item["created_at"], item["id"]))
    assert records.json() == client.get(URL).json()
    with UnitOfWork() as uow:
        assert uow.session.scalar(select(ApplicationProfile).where(ApplicationProfile.user_id == owner)) is None
        assert uow.session.get(EducationRecord, UUID(first["id"])).user_id == owner


@pytest.mark.parametrize("method,id", [("GET", None), ("POST", None), ("PATCH", str(uuid4())), ("DELETE", str(uuid4()))])
def test_unauthenticated_rejected(method, id):
    response = TestClient(app).request(method, URL + (f"/{id}" if id else ""), json=FACTS if method in {"POST", "PATCH"} else None)
    assert response.status_code == 401


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
def test_csrf_for_every_mutation(method):
    client, _ = register()
    other, _ = register()
    record = create(client)
    path = URL if method == "POST" else f"{URL}/{record['id']}"
    for token in (None, "wrong", other.cookies["ss_csrf"]):
        response = client.request(method, path, json=FACTS if method != "DELETE" else None,
                                  headers={} if token is None else {"X-CSRF-Token": token})
        assert response.status_code == 403
    assert client.get(URL).json() == [record]
    assert mutate(client, method, FACTS if method != "DELETE" else None, None if method == "POST" else record["id"]).status_code == {"POST": 201, "PATCH": 200, "DELETE": 204}[method]


def test_idor_body_query_injection_and_safe_not_found():
    first, first_id = register()
    second, _ = register()
    record = create(first)
    assert second.get(URL).json() == []
    assert second.get(f"{URL}?user_id={first_id}").status_code == 422
    assert mutate(second, "POST", {**FACTS, "user_id": str(first_id)}).status_code == 422
    for method in ("PATCH", "DELETE"):
        responses = [mutate(second, method, {"major": "changed"} if method == "PATCH" else None, id) for id in (record["id"], str(uuid4()))]
        assert all(response.status_code == 404 for response in responses)
        assert responses[0].json()["code"] == responses[1].json()["code"] == "EDUCATION_NOT_FOUND"
        assert responses[0].json()["detail"] == responses[1].json()["detail"]
    assert mutate(first, "PATCH", {"user_id": str(uuid4())}, record["id"]).status_code == 422
    assert first.get(URL).json() == [record]


def test_partial_update_optional_clear_and_delete():
    client, _ = register()
    first = create(client, minor="Art")
    second = create(client, institution_name="Second")
    response = mutate(client, "PATCH", {"major": "Physics"}, first["id"])
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    for key in first.keys() - {"major", "updated_at"}:
        assert response.json()[key] == first[key]
    assert response.json()["major"] == "Physics"
    assert mutate(client, "PATCH", {"minor": None}, first["id"]).json()["minor"] is None
    assert mutate(client, "PATCH", {"minor": " "}, first["id"]).json()["minor"] is None
    response = mutate(client, "DELETE", id=first["id"])
    assert response.status_code == 204 and response.content == b""
    assert response.headers["cache-control"] == "no-store"
    assert client.get(URL).json() == [second]
    assert mutate(client, "DELETE", id=first["id"]).status_code == 404


@pytest.mark.parametrize("value,scale", [("3.54", "4.00"), ("4.20", "4.33"), ("10.00", "10.00"), ("85.00", "100.00"), ("100.00", "100.00"), ("0.00", "4.00"), ("999.99", "999.99")])
def test_native_decimal_scales(value, scale):
    client, _ = register()
    record = create(client, gpa_value=value, gpa_scale=scale, gpa_include_on_apps=True)
    assert record["gpa_value"] == value and record["gpa_scale"] == scale
    assert client.get(URL).json()[0] == record


@pytest.mark.parametrize("payload", [
    {"degree_level": "BACHELOR"}, {"study_year": "FIRST"}, {"institution_name": " "},
    {"institution_name": "x" * 256}, {"major": "x" * 151}, {"minor": "x" * 151},
    {"expected_grad_month": 0}, {"expected_grad_month": 13}, {"expected_grad_year": 1999}, {"expected_grad_year": 2101},
    {"expected_grad_month": 1.2}, {"start_date": "2030-01-01"},
    {"gpa_value": "3.80"}, {"gpa_scale": "4.00"}, {"gpa_value": "5.00", "gpa_scale": "4.00"},
    {"gpa_value": "-0.01", "gpa_scale": "4.00"}, {"gpa_value": "0", "gpa_scale": "0"},
    {"gpa_value": "0", "gpa_scale": "-1"}, {"gpa_value": "3.541", "gpa_scale": "4.00"},
    {"gpa_value": "3.54", "gpa_scale": "4.001"}, {"gpa_value": "1000", "gpa_scale": "1000"},
    {"gpa_value": "NaN", "gpa_scale": "4.00"}, {"gpa_include_on_apps": True},
    {"gpa_include_on_apps": None}, {"is_primary": None}, {"citizenship": "CA"},
])
def test_invalid_create_and_patch_do_not_write(payload):
    client, _ = register()
    assert mutate(client, "POST", {**FACTS, **payload}).status_code == 422
    assert client.get(URL).json() == []
    record = create(client)
    assert mutate(client, "PATCH", payload, record["id"]).status_code == 422
    assert client.get(URL).json() == [record]


@pytest.mark.parametrize("field", [*FACTS, "gpa_include_on_apps", "is_primary"])
def test_nonnullable_patch_cannot_clear(field):
    client, _ = register()
    record = create(client)
    assert mutate(client, "PATCH", {field: None}, record["id"]).status_code == 422
    assert client.get(URL).json() == [record]


def test_final_state_gpa_and_dates_before_any_primary_changes():
    client, _ = register()
    first = create(client, is_primary=True)
    record = create(client, gpa_value="3.54", gpa_scale="4.00", gpa_include_on_apps=True)
    for changes in ({"gpa_scale": None}, {"gpa_value": None}, {"gpa_scale": "3.00"},
                    {"gpa_value": None, "gpa_scale": None}, {"expected_grad_year": 2020}):
        assert mutate(client, "PATCH", {**changes, "is_primary": True}, record["id"]).status_code == 422
        assert client.get(URL).json() == [first, record]
    assert mutate(client, "PATCH", {"gpa_value": "3.80"}, record["id"]).status_code == 200
    result = mutate(client, "PATCH", {"gpa_value": None, "gpa_scale": None, "gpa_include_on_apps": False}, record["id"])
    assert result.status_code == 200
    assert result.json()["gpa_value"] is None and result.json()["gpa_scale"] is None
    assert result.json()["gpa_include_on_apps"] is False
    assert mutate(client, "PATCH", {"gpa_value": "3.80"}, record["id"]).status_code == 422


@pytest.mark.parametrize("start,month,year", [("2000-01-31", 1, 2000), ("2100-12-31", 12, 2100), ("2028-06-30", 6, 2028)])
def test_graduation_boundaries_and_same_month(start, month, year):
    client, _ = register()
    record = create(client, start_date=start, expected_grad_month=month, expected_grad_year=year)
    assert record["start_date"] == start


def test_primary_is_explicit_single_per_owner_and_no_auto_promotion():
    client, _ = register()
    other, _ = register()
    other_record = create(other, is_primary=True)
    first = create(client)
    second = create(client, institution_name="Second", is_primary=True)
    assert [r["is_primary"] for r in client.get(URL).json()] == [False, True]
    assert mutate(client, "PATCH", {"is_primary": True}, first["id"]).status_code == 200
    assert [r["is_primary"] for r in client.get(URL).json()] == [True, False]
    third = create(client, institution_name="Third", is_primary=True)
    assert [r["is_primary"] for r in client.get(URL).json()] == [False, False, True]
    assert mutate(client, "DELETE", id=third["id"]).status_code == 204
    assert [r["id"] for r in client.get(URL).json()] == [first["id"], second["id"]]
    assert all(not r["is_primary"] for r in client.get(URL).json())
    assert other.get(URL).json() == [other_record]


def test_commits_and_concurrent_primary_changes(database_engine):
    factory = sessionmaker(bind=database_engine)
    owner = uuid4()
    try:
        with factory.begin() as session:
            session.add(User(id=owner, email=f"edu-commit-{owner}@example.com", password_hash="test"))
        with UnitOfWork(factory) as uow:
            first = EducationService.create(owner, EducationCreate(**FACTS), uow)
        with factory() as session:
            assert session.get(EducationRecord, first.id).start_date == date(2024, 9, 1)
        with UnitOfWork(factory) as uow:
            EducationService.update(owner, first.id, EducationUpdate(gpa_value=Decimal("100.00"), gpa_scale=Decimal("100.00")), uow)
        with factory() as session:
            assert session.get(EducationRecord, first.id).gpa_value == Decimal("100.00")
        barrier = Barrier(2)

        def concurrent_primary(index):
            barrier.wait(timeout=10)
            with UnitOfWork(factory) as uow:
                return EducationService.create(owner, EducationCreate(**{**FACTS, "institution_name": f"Concurrent {index}", "is_primary": True}), uow)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(concurrent_primary, index) for index in range(2)]
            assert len({future.result(timeout=20).id for future in futures}) == 2
        with factory() as session:
            records = list(session.scalars(select(EducationRecord).where(EducationRecord.user_id == owner)))
            assert len(records) == 3
            assert sum(record.is_primary for record in records) == 1
        with UnitOfWork(factory) as uow:
            EducationService.delete(owner, first.id, uow)
        with factory() as session:
            assert session.get(EducationRecord, first.id) is None
    finally:
        with factory.begin() as session:
            session.execute(delete(User).where(User.id == owner))
