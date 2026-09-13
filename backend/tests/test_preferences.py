"""Preference replacement, read-only catalogs, isolation and committed concurrency."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.main import app
from backend.app.models.preference import (
    CareerPreference,
    CareerPreferenceCustomValue,
    UserPreferredRole,
    UserPreferredSkill,
)
from backend.app.models.resume import UserSkill
from backend.app.models.taxonomy import Company, Industry, Location, Role, Skill
from backend.app.models.user import User
from backend.app.schemas.preferences import Preferences
from backend.app.services.preferences import PreferencesService

URL = "/api/v1/preferences"


def register():
    client = TestClient(app)
    response = client.post("/api/v1/auth/register", json={"email": f"pref-{uuid4().hex}@example.com", "password": "Preferences-password-123!"})
    assert response.status_code == 201
    return client, UUID(response.json()["user"]["id"])


def put(client, values):
    return client.put(URL, json=values, headers={"X-CSRF-Token": client.cookies["ss_csrf"]})


@pytest.fixture
def catalog(isolated_database):
    rows = [Role(name="Alpha role", slug="alpha"), Role(name="Beta role", slug="beta"), Role(name="Hidden role", slug="hidden", is_active=False),
            Skill(name="Python", slug="python", category="LANGUAGE"), Skill(name="React", slug="react", category="FRAMEWORK"), Skill(name="Hidden skill", slug="hidden", category="LANGUAGE", is_active=False),
            Industry(name="Technology", slug="technology"), Company(name="Example Company"), Company(name="100% Company"),
            Location(country_code="CA", state_province="Alberta", city="Calgary"), Location(country_code="US", state_province="Colorado", city="Denver")]
    with UnitOfWork() as uow:
        uow.session.add_all(rows)
        uow.commit()
        result = [row.id for row in rows]
    return result


def test_empty_get_does_not_create_and_empty_put_does():
    client, owner = register()
    response = client.get(URL)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json() == Preferences().model_dump(mode="json")
    with UnitOfWork() as uow:
        assert uow.session.scalar(select(CareerPreference).where(CareerPreference.user_id == owner)) is None
    assert put(client, {}).status_code == 200
    with UnitOfWork() as uow:
        assert uow.session.scalar(select(CareerPreference).where(CareerPreference.user_id == owner)) is not None


def test_complete_replacement_idempotence_and_no_skill_claim(catalog):
    client, owner = register()
    payload = dict(role_ids=list(map(str, catalog[:2])), skill_ids=list(map(str, catalog[3:5])), industry_ids=[str(catalog[6])], company_ids=[str(catalog[7])], location_ids=[str(catalog[9])],
                   work_modes=["REMOTE", "HYBRID"], employment_types=["CO_OP", "INTERNSHIP"], custom_values=[{"preference_type": "ROLE", "value": "  My   Role  "}, {"preference_type": "SKILL", "value": "Python"}])
    result = put(client, payload)
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    assert result.json() == Preferences(**payload).model_dump(mode="json")
    assert client.get(URL).json() == result.json()
    with UnitOfWork() as uow:
        root = uow.session.scalar(select(CareerPreference).where(CareerPreference.user_id == owner))
        root_id, updated = root.id, root.updated_at
        before = [(x.id, x.normalized_value, x.value) for x in uow.session.scalars(select(CareerPreferenceCustomValue).where(CareerPreferenceCustomValue.career_preference_id == root_id).order_by(CareerPreferenceCustomValue.id))]
        assert any(x[1:] == ("my role", "  My   Role  ") for x in before)
        assert uow.session.scalar(select(UserSkill).where(UserSkill.user_id == owner)) is None
        assert len(list(uow.session.scalars(select(UserPreferredSkill).where(UserPreferredSkill.user_id == owner)))) == 2
    assert put(client, payload).json() == result.json()
    with UnitOfWork() as uow:
        assert uow.session.get(CareerPreference, root_id).updated_at == updated
        assert [(x.id, x.normalized_value, x.value) for x in uow.session.scalars(select(CareerPreferenceCustomValue).where(CareerPreferenceCustomValue.career_preference_id == root_id).order_by(CareerPreferenceCustomValue.id))] == before
    replacement = {"role_ids": [str(catalog[1])], "work_modes": ["ON_SITE"]}
    assert put(client, replacement).json() == Preferences(**replacement).model_dump(mode="json")
    assert client.get(URL).json() == Preferences(**replacement).model_dump(mode="json")
    with UnitOfWork() as uow:
        assert uow.session.scalar(select(UserPreferredSkill).where(UserPreferredSkill.user_id == owner)) is None
        assert uow.session.scalar(select(CareerPreferenceCustomValue).where(CareerPreferenceCustomValue.career_preference_id == root_id)) is None


@pytest.mark.parametrize("field", ["role_ids", "industry_ids", "company_ids", "location_ids", "skill_ids"])
def test_invalid_catalog_id_never_partially_erases(field, catalog):
    client, _ = register()
    saved = put(client, {"role_ids": [str(catalog[0])], "custom_values": [{"preference_type": "ROLE", "value": "Keep"}]}).json()
    response = put(client, {field: [str(uuid4())]})
    assert response.status_code == 422 and response.json()["code"] == "INVALID_PREFERENCE_SELECTION"
    assert client.get(URL).json() == saved


@pytest.mark.parametrize("payload", [
    {"work_modes": ["UNSPECIFIED"]}, {"employment_types": ["FULL_TIME"]}, {"work_modes": [None]}, {"work_modes": None},
    {"role_ids": ["bad"]}, {"custom_values": [{"preference_type": "UNKNOWN", "value": "X"}]},
    {"custom_values": [{"preference_type": "ROLE", "value": "  "}]}, {"custom_values": [{"preference_type": "ROLE", "value": "x" * 151}]},
    {"custom_values": [{"preference_type": "ROLE", "value": " My   Role "}, {"preference_type": "ROLE", "value": "my role"}]},
    {"custom_values": [{"preference_type": "ROLE", "value": "Straße"}, {"preference_type": "ROLE", "value": "STRASSE"}]},
    {"user_id": str(uuid4())}, {"custom_values": [{"preference_type": "ROLE", "value": "X", "normalized_value": "hack"}]}
])
def test_invalid_input_preserves_saved_aggregate(payload):
    client, _ = register()
    saved = put(client, {"work_modes": ["REMOTE"]}).json()
    assert put(client, payload).status_code == 422
    assert client.get(URL).json() == saved


def test_dedupe_canonical_choices_and_keep_separate_custom_types(catalog):
    client, _ = register()
    payload = {"role_ids": [str(catalog[0])] * 2, "work_modes": ["REMOTE"] * 2, "custom_values": [{"preference_type": t, "value": "Example"} for t in ["ROLE", "COMPANY"]]}
    result = put(client, payload)
    assert result.status_code == 200
    assert len(result.json()["role_ids"]) == 1 and result.json()["work_modes"] == ["REMOTE"]
    assert len(result.json()["custom_values"]) == 2


def test_session_isolation_ownership_and_csrf():
    a, owner = register()
    b, _ = register()
    saved = put(a, {"work_modes": ["REMOTE"]}).json()
    assert b.get(URL).json() == Preferences().model_dump(mode="json")
    assert put(b, {"work_modes": ["HYBRID"]}).status_code == 200
    for method in ["GET", "PUT"]:
        assert b.request(method, URL + f"?user_id={owner}", json={}, headers={"X-CSRF-Token": b.cookies["ss_csrf"]}).status_code == 422
    for token in [None, "wrong", b.cookies["ss_csrf"]]:
        assert a.put(URL, json={}, headers={} if token is None else {"X-CSRF-Token": token}).status_code == 403
    assert a.get(URL).json() == saved
    assert TestClient(app).get(URL).status_code == 401
    assert TestClient(app).put(URL, json={}).status_code == 401


def test_catalog_filters_order_active_and_read_only(catalog):
    client, _ = register()
    def ids(path):
        response = client.get("/api/v1/catalog/" + path)
        assert response.status_code == 200
        return [x["id"] for x in response.json()]
    assert ids("roles") == list(map(str, catalog[:2]))
    assert ids("roles?q=ALPHA") == [str(catalog[0])]
    assert ids("roles?active=false") == [str(catalog[2])]
    assert ids("skills") == list(map(str, catalog[3:5]))
    assert ids("skills?category=LANGUAGE&q=py") == [str(catalog[3])]
    assert ids("industries") == [str(catalog[6])]
    assert ids("companies?q=%25") == [str(catalog[8])]
    assert ids("companies") == list(map(str, [catalog[8], catalog[7]]))
    assert ids("locations?country_code=ca&q=alberta") == [str(catalog[9])]
    assert ids("locations") == list(map(str, catalog[9:11]))
    for name in ["roles", "skills", "industries", "companies", "locations"]:
        assert TestClient(app).get("/api/v1/catalog/"+name).status_code == 401
        assert client.post("/api/v1/catalog/"+name, json={}).status_code == 405


def test_committed_persistence_and_concurrent_complete_replacement(database_engine, monkeypatch):
    from backend.app.core import unit_of_work
    factory = sessionmaker(bind=database_engine, expire_on_commit=False)
    monkeypatch.setattr(unit_of_work, "SessionLocal", factory)
    client, owner = register()
    role_ids = [uuid4(), uuid4()]
    try:
        with factory.begin() as session:
            session.add_all([Role(id=id, name=str(id), slug=str(id)) for id in role_ids])
        payloads = [Preferences(role_ids=[id], work_modes=[mode], custom_values=[{"preference_type": "ROLE", "value": mode}]) for id, mode in zip(role_ids, ["REMOTE", "HYBRID"])]
        assert put(client, payloads[0].model_dump(mode="json")).status_code == 200
        with factory() as session:
            assert list(session.scalars(select(UserPreferredRole.role_id).where(UserPreferredRole.user_id == owner))) == [role_ids[0]]
        barrier = Barrier(2)
        def writer(index):
            with UnitOfWork(factory) as uow:
                barrier.wait(timeout=10)
                return PreferencesService.replace(owner, payloads[index], uow)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(writer, [0, 1]))
        result = client.get(URL).json()
        assert result in [x.model_dump(mode="json") for x in payloads]
        assert put(client, {}).status_code == 200
        with factory() as session:
            assert not list(session.scalars(select(UserPreferredRole).where(UserPreferredRole.user_id == owner)))
            root = session.scalar(select(CareerPreference).where(CareerPreference.user_id == owner))
            assert not list(session.scalars(select(CareerPreferenceCustomValue).where(CareerPreferenceCustomValue.career_preference_id == root.id)))
    finally:
        with factory.begin() as session:
            session.execute(delete(User).where(User.id == owner))
            session.execute(delete(Role).where(Role.id.in_(role_ids)))

