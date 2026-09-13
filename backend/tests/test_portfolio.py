"""Skills/project factual separation, atomic writes and real PostgreSQL contention."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.main import app
from backend.app.models.portfolio import UserCustomSkill
from backend.app.models.resume import UserSkill
from backend.app.models.taxonomy import Skill, SkillAlias
from backend.app.models.user import User
from backend.app.schemas.portfolio import SkillSelection
from backend.app.services.portfolio import PortfolioService

SKILLS = "/api/v1/profile/skills"
PROJECTS = "/api/v1/profile/projects"


def account():
    c = TestClient(app)
    response = c.post(
        "/api/v1/auth/register",
        json={"email": f"portfolio-{uuid4()}@example.com", "password": "Password123!"},
    )
    assert response.status_code == 201
    c.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return c, UUID(response.json()["user"]["id"])


@pytest.fixture
def catalog(isolated_database):
    ids = [uuid4(), uuid4()]
    isolated_database.execute(
        Skill.__table__.insert(),
        [
            {"id": id, "name": name, "slug": str(id), "category": "TECHNOLOGY"}
            for id, name in zip(ids, ["Python", "PostgreSQL"])
        ],
    )
    isolated_database.execute(
        SkillAlias.__table__.insert(), {"skill_id": ids[0], "alias": "Py", "normalized_alias": "py"}
    )
    return list(map(str, ids))


def test_empty_and_preference_independence():
    c, _ = account()
    assert c.get(SKILLS).json() == {"skill_ids": [], "custom_values": []}
    assert c.get(PROJECTS).json() == []
    saved = c.put(
        "/api/v1/preferences",
        json={"custom_values": [{"preference_type": "SKILL", "value": "Interest only"}]},
    ).json()
    assert c.get(SKILLS).json() == {"skill_ids": [], "custom_values": []}
    assert c.put(SKILLS, json={"custom_values": ["Actual claim"]}).status_code == 200
    assert c.get("/api/v1/preferences").json() == saved


def test_skills_save_remove_preserve_text_metadata_and_single_commit(catalog, isolated_database):
    c, owner = account()
    values = {
        "skill_ids": catalog + catalog[:1],
        "custom_values": ["  Linux scripting  ", "Other ability"],
    }
    original = UnitOfWork.commit
    with patch.object(UnitOfWork, "commit", autospec=True, side_effect=original) as commit:
        result = c.put(SKILLS, json=values)
        assert result.status_code == 200, result.text
        assert commit.call_count == 1
    saved = result.json()
    assert len(saved["skill_ids"]) == 2 and "  Linux scripting  " in saved["custom_values"]
    before = list(
        isolated_database.execute(
            select(UserSkill.__table__).where(UserSkill.user_id == owner)
        ).mappings()
    )
    customs = list(
        isolated_database.execute(
            select(UserCustomSkill.__table__).where(UserCustomSkill.user_id == owner)
        ).mappings()
    )
    assert all(row["confirmed_by_user"] and row["source"] == "USER" for row in before)
    for _ in range(2):
        assert c.put(SKILLS, json=values).json() == saved
    assert (
        list(
            isolated_database.execute(
                select(UserSkill.__table__).where(UserSkill.user_id == owner)
            ).mappings()
        )
        == before
    )
    assert (
        list(
            isolated_database.execute(
                select(UserCustomSkill.__table__).where(UserCustomSkill.user_id == owner)
            ).mappings()
        )
        == customs
    )
    assert c.get(SKILLS).json() == saved
    assert c.put(SKILLS, json={"skill_ids": catalog[:1]}).json() == {
        "skill_ids": catalog[:1],
        "custom_values": [],
    }
    assert c.put(SKILLS, json={}).json() == {"skill_ids": [], "custom_values": []}


@pytest.mark.parametrize(
    "bad",
    [
        {"skill_ids": [str(uuid4())]},
        {"skill_ids": ["bad"]},
        {"custom_values": [" "]},
        {"custom_values": ["x" * 151]},
        {"custom_values": [" My  Skill ", "my skill"]},
        {"custom_values": ["Straße", "STRASSE"]},
        {"custom_values": [" python "]},
        {"custom_values": ["PY"]},
        {"user_id": str(uuid4())},
        {"custom_values": None},
        {"skill_ids": None},
    ],
)
def test_bad_skills_preserve_existing(bad, catalog):
    c, _ = account()
    saved = c.put(SKILLS, json={"skill_ids": catalog[:1], "custom_values": ["Saved"]}).json()
    assert c.put(SKILLS, json=bad).status_code == 422
    assert c.get(SKILLS).json() == saved


def test_existing_confirmed_rows_reused_without_overwriting_metadata(catalog, isolated_database):
    c, owner = account()
    isolated_database.execute(
        UserSkill.__table__.insert(),
        {
            "user_id": owner,
            "skill_id": UUID(catalog[0]),
            "source": "USER",
            "user_notes": "Preserve note",
            "confirmed_by_user": True,
        },
    )
    before = dict(
        isolated_database.execute(select(UserSkill.__table__).where(UserSkill.user_id == owner))
        .mappings()
        .one()
    )
    assert c.get(SKILLS).json()["skill_ids"] == catalog[:1]
    assert c.put(SKILLS, json={"skill_ids": catalog[:1]}).status_code == 200
    assert (
        dict(
            isolated_database.execute(select(UserSkill.__table__).where(UserSkill.user_id == owner))
            .mappings()
            .one()
        )
        == before
    )


def test_projects_crud_multiple_and_separate_technologies(catalog):
    c, _ = account()
    skills = c.put(
        SKILLS, json={"skill_ids": catalog[:1], "custom_values": ["User-only skill"]}
    ).json()
    prefs = c.put(
        "/api/v1/preferences",
        json={"custom_values": [{"preference_type": "SKILL", "value": "Interest"}]},
    ).json()
    payload = {
        "title": "  My project  ",
        "description": "<b>Explicit description</b>",
        "technologies": {"skill_ids": catalog[1:], "custom_values": ["  Project-only ability  "]},
        "project_url": "https://example.com/demo",
        "repository_url": "https://example.com/repo",
    }
    result = c.post(PROJECTS, json=payload)
    assert result.status_code == 201, result.text
    first = result.json()
    id = first["id"]
    assert all(first[key] == value for key, value in payload.items())
    assert c.get(PROJECTS + "/" + id).json() == first
    second = c.post(PROJECTS, json={"title": "Second"}).json()
    assert [row["id"] for row in c.get(PROJECTS).json()] == [id, second["id"]]
    assert c.get(SKILLS).json() == skills
    updated = c.patch(
        PROJECTS + "/" + id,
        json={"title": "Updated", "technologies": {"custom_values": ["New technology"]}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["description"] == payload["description"]
    assert updated.json()["technologies"] == {"skill_ids": [], "custom_values": ["New technology"]}
    assert (
        c.patch(PROJECTS + "/" + id, json={"repository_url": None}).json()["repository_url"] is None
    )
    assert c.get(SKILLS).json() == skills
    assert c.delete(PROJECTS + "/" + id).status_code == 204
    assert c.get(PROJECTS + "/" + id).status_code == 404
    assert c.get(PROJECTS).json() == [second]
    assert c.get(SKILLS).json() == skills and c.get("/api/v1/preferences").json() == prefs


@pytest.mark.parametrize(
    "bad",
    [
        {"title": ""},
        {"title": " "},
        {"title": None},
        {"description": "x" * 5001},
        {"project_url": "javascript:alert(1)"},
        {"repository_url": "https://user:password@example.com"},
        {"project_url": "https://example.com/a b"},
        {"project_url": "https://example.com:bad"},
        {"repository_url": 123},
        {"technologies": {"skill_ids": [str(uuid4())]}},
        {"technologies": {"custom_values": ["Same", " same "]}},
        {"technologies": None},
        {"user_id": str(uuid4())},
    ],
)
def test_bad_project_create_and_update_preserve_data(bad):
    c, _ = account()
    saved = c.post(
        PROJECTS,
        json={"title": "Saved", "description": "Keep", "technologies": {"custom_values": ["Kept"]}},
    ).json()
    assert c.post(PROJECTS, json={"title": "New", **bad}).status_code == 422
    response = c.patch(PROJECTS + "/" + saved["id"], json=bad)
    assert response.status_code == 422, response.text
    assert c.get(PROJECTS).json() == [saved]


def test_ownership_authentication_and_csrf(catalog):
    a, _ = account()
    b, other = account()
    record = a.post(PROJECTS, json={"title": "Private"}).json()
    id = record["id"]
    assert a.put(SKILLS, json={"skill_ids": catalog[:1]}).status_code == 200
    assert b.get(SKILLS).json() == {"skill_ids": [], "custom_values": []}
    assert b.get(PROJECTS).json() == []
    for method in ["GET", "PATCH", "DELETE"]:
        assert (
            b.request(
                method, PROJECTS + "/" + id, json={} if method == "PATCH" else None
            ).status_code
            == 404
        )
    for path in [SKILLS, PROJECTS]:
        assert a.get(path + f"?user_id={other}").status_code == 422
        assert TestClient(app).get(path).status_code == 401
    for method, path, payload in [
        ("PUT", SKILLS, {}),
        ("POST", PROJECTS, {"title": "Test"}),
        ("PATCH", PROJECTS + "/" + id, {"title": "Test"}),
        ("DELETE", PROJECTS + "/" + id, None),
    ]:
        assert TestClient(app).request(method, path, json=payload).status_code == 401
        assert (
            a.request(method, path, json=payload, headers={"X-CSRF-Token": "wrong"}).status_code
            == 403
        )
    assert a.get(PROJECTS).json() == [record]


def test_committed_skills_concurrency_no_mixed_aggregate(database_engine, monkeypatch):
    from backend.app.core import unit_of_work

    factory = sessionmaker(bind=database_engine, expire_on_commit=False)
    monkeypatch.setattr(unit_of_work, "SessionLocal", factory)
    c, owner = account()
    ids = [uuid4(), uuid4()]
    try:
        with factory.begin() as s:
            s.add_all(
                [Skill(id=id, name=str(id), slug=str(id), category="TECHNOLOGY") for id in ids]
            )
        values = [
            SkillSelection(skill_ids=[id], custom_values=[name])
            for id, name in zip(ids, ["Left claim", "Right claim"])
        ]
        barrier = Barrier(2)

        def save(index):
            with UnitOfWork(factory) as uow:
                barrier.wait(timeout=10)
                return PortfolioService.skills(owner, uow, values[index])

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(save, [0, 1]))
        assert c.get(SKILLS).json() in [value.model_dump(mode="json") for value in values]
        with factory() as s:
            assert len(list(s.scalars(select(UserSkill).where(UserSkill.user_id == owner)))) == 1
    finally:
        with factory.begin() as s:
            s.execute(delete(User).where(User.id == owner))
            s.execute(delete(Skill).where(Skill.id.in_(ids)))
