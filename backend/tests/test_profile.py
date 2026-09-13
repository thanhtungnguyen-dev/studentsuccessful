"""Application facts, ownership and PATCH behavior against disposable PostgreSQL."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.main import app
from backend.app.models.profile import ApplicationProfile
from backend.app.models.user import User
from backend.app.schemas.profile import ProfileUpdate
from backend.app.services.profile import ApplicationProfileService

URL = "/api/v1/profile"
FACTS = {
    "legal_first_name": "李 Anne", "legal_middle_name": "Marie",
    "legal_last_name": "O’Neill", "preferred_name": "Annie",
    "phone_number": "+1 (403) 555-0100 ext. 12",
    "address_street": "123 Example Street\nSuite 4", "address_city": "Calgary",
    "address_state_province": "Alberta", "address_postal_code": "T2P 1J9",
    "address_country_code": "CA", "linkedin_url": "https://linkedin.com/in/example",
    "github_url": "https://github.com/example",
    "portfolio_url": "https://example.com/Portfolio?view=One#work",
}
OPTIONAL = set(FACTS) - {"legal_first_name", "legal_last_name"}


def register():
    client = TestClient(app)
    result = client.post("/api/v1/auth/register", json={
        "email": f"profile-{uuid4().hex}@example.com", "password": "Profile-password-123!",
    })
    assert result.status_code == 201
    return client, UUID(result.json()["user"]["id"])


def patch(client, payload):
    return client.patch(URL, json=payload, headers={"X-CSRF-Token": client.cookies["ss_csrf"]})


def test_unauthenticated_read_and_update_rejected():
    client = TestClient(app)
    assert client.get(URL).status_code == 401
    assert client.patch(URL, json=FACTS).status_code == 401


def test_read_absent_does_not_create_or_infer_and_first_save_requires_names():
    client, user_id = register()
    assert client.get(URL).json() is None
    result = patch(client, {"preferred_name": "Me"})
    assert result.status_code == 422
    assert {tuple(error["loc"]) for error in result.json()["detail"]} == {
        ("body", "legal_first_name"), ("body", "legal_last_name"),
    }
    with UnitOfWork() as uow:
        assert uow.session.scalar(select(ApplicationProfile).where(
            ApplicationProfile.user_id == user_id)) is None
    result = patch(client, {"legal_first_name": "李", "legal_last_name": "O’Neill"})
    assert result.status_code == 200
    assert all(result.json()[key] is None for key in OPTIONAL)


def test_all_facts_trim_persist_and_partial_patch_preserves_omissions():
    client, _ = register()
    payload = {key: f"  {value}  " for key, value in FACTS.items()}
    payload["address_country_code"] = " ca "
    result = patch(client, payload)
    assert result.status_code == 200
    assert result.json() == FACTS
    assert result.headers["cache-control"] == "no-store"
    assert patch(client, {"preferred_name": "Changed"}).json() == {
        **FACTS, "preferred_name": "Changed",
    }
    assert patch(client, {}).json() == {**FACTS, "preferred_name": "Changed"}
    response = client.get(URL)
    assert response.json() == {**FACTS, "preferred_name": "Changed"}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("key", sorted(OPTIONAL))
@pytest.mark.parametrize("clear", [None, "  "])
def test_optional_clear_preserves_other_facts(key, clear):
    client, _ = register()
    assert patch(client, FACTS).status_code == 200
    assert patch(client, {key: clear}).json() == {**FACTS, key: None}
    assert client.get(URL).json() == {**FACTS, key: None}


@pytest.mark.parametrize("payload", [
    {"legal_first_name": None}, {"legal_last_name": " "},
    {"legal_first_name": "x" * 101}, {"preferred_name": "x" * 101},
    {"address_street": "x" * 256}, {"address_city": "x" * 101},
    {"address_state_province": "x" * 101}, {"address_postal_code": "x" * 31},
    {"phone_number": "1" * 31}, {"phone_number": "call me"},
    {"phone_number": "123"}, {"address_country_code": "Canada"},
    {"address_country_code": "1A"}, {"legal_middle_name": "x" * 101},
    {"portfolio_url": "https://example.com/" + "x" * 500},
    {"user_id": str(uuid4())}, {"id": str(uuid4())}, {"email": "other@example.com"},
    {"citizenship": "CA"}, {"desired_locations": ["Calgary"]}, {"skills": ["Python"]},
])
def test_invalid_input_rejected_without_partial_write(payload):
    client, _ = register()
    assert patch(client, FACTS).status_code == 200
    assert patch(client, {**payload, "preferred_name": payload.get("preferred_name", "Changed")}).status_code == 422
    assert client.get(URL).json() == FACTS


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "file:///etc/passwd", "data:text/plain,no", "ftp://example.com",
    "example.com", "https://", "https://exa mple.com", "https://example.com:bad",
    "https://user:password@example.com", "https://example.com\\evil", "https://example.com/\npath",
])
@pytest.mark.parametrize("field", ["linkedin_url", "github_url", "portfolio_url"])
def test_unsafe_or_invalid_web_links_rejected(field, url):
    client, _ = register()
    assert patch(client, {**FACTS, field: url}).status_code == 422
    assert client.get(URL).json() is None


def test_owner_is_always_session_user():
    first, first_id = register()
    second, second_id = register()
    assert patch(first, FACTS).status_code == 200
    assert second.get(f"{URL}?user_id={first_id}").json() is None
    assert patch(second, {**FACTS, "user_id": str(first_id)}).status_code == 422
    assert patch(second, {**FACTS, "preferred_name": "Second"}).status_code == 200
    assert first.get(f"{URL}?user_id={second_id}").json() == FACTS
    assert first.patch(f"{URL}?user_id={second_id}", json={"preferred_name": "First"},
                       headers={"X-CSRF-Token": first.cookies["ss_csrf"]}).status_code == 200
    assert second.get(URL).json() == {**FACTS, "preferred_name": "Second"}
    assert first.get(f"{URL}/{second_id}").status_code == 404


def test_csrf_is_required_and_bound_to_current_session():
    client, _ = register()
    other, _ = register()
    for headers in ({}, {"X-CSRF-Token": "bad"},
                    {"X-CSRF-Token": other.cookies["ss_csrf"]}):
        assert client.patch(URL, json=FACTS, headers=headers).status_code == 403
    assert client.get(URL).json() is None
    assert patch(client, FACTS).status_code == 200


def test_service_commit_visible_to_independent_database_session(database_engine):
    factory = sessionmaker(bind=database_engine)
    user_id = uuid4()
    try:
        with factory.begin() as session:
            session.add(User(id=user_id, email=f"commit-{user_id}@example.com", password_hash="test"))
        with UnitOfWork(factory) as uow:
            ApplicationProfileService.update(user_id, ProfileUpdate(**FACTS), uow)
        with factory() as independent:
            profile = independent.scalar(select(ApplicationProfile).where(ApplicationProfile.user_id == user_id))
            assert profile is not None
            assert profile.preferred_name == FACTS["preferred_name"]
            assert profile.address_street == FACTS["address_street"]
        with UnitOfWork(factory) as uow:
            ApplicationProfileService.update(user_id, ProfileUpdate(preferred_name=None), uow)
        with factory() as independent:
            profile = independent.scalar(select(ApplicationProfile).where(ApplicationProfile.user_id == user_id))
            assert profile.preferred_name is None
            assert profile.legal_first_name == FACTS["legal_first_name"]
    finally:
        with factory.begin() as session:
            session.execute(delete(User).where(User.id == user_id))
