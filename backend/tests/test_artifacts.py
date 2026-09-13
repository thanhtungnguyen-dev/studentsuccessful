"""Linked Resume CRUD, validation, ownership and full domain independence."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.main import app
from backend.app.models.base import Base
from backend.tests.test_portfolio import account

URL = "/api/v1/artifacts"


def test_crud_multiple_persistence_single_commit_and_independence(isolated_database):
    c, owner = account()
    assert c.get(URL).json() == []
    writes = [
        ("PATCH", "/profile", {"legal_first_name": "Ada", "legal_last_name": "Lovelace"}),
        (
            "POST",
            "/profile/education",
            {
                "institution_name": "Example",
                "degree_level": "BS",
                "major": "Computing",
                "study_year": "YEAR_2",
                "start_date": "2025-01-01",
                "expected_grad_month": 5,
                "expected_grad_year": 2028,
                "is_primary": True,
            },
        ),
        (
            "POST",
            "/profile/employment",
            {
                "employer_name": "Example",
                "job_title": "Developer",
                "start_date": "2026-01-01",
                "currently_employed": True,
            },
        ),
        (
            "POST",
            "/profile/work-authorizations",
            {
                "country_code": "CA",
                "authorization_status": "OTHER",
                "requires_current_sponsorship": False,
                "requires_future_sponsorship": True,
            },
        ),
        ("PUT", "/profile/skills", {"custom_values": ["Explicit skill"]}),
        (
            "POST",
            "/profile/projects",
            {"title": "Existing project", "technologies": {"custom_values": ["Project tech"]}},
        ),
        (
            "PUT",
            "/preferences",
            {"custom_values": [{"preference_type": "SKILL", "value": "Interest"}]},
        ),
    ]
    for method, path, data in writes:
        response = c.request(method, "/api/v1" + path, json=data)
        assert response.status_code in [200, 201], response.text

    def snapshot():
        return {
            table.name: list(isolated_database.execute(select(table)).mappings())
            for table in Base.metadata.sorted_tables
            if table.name != "career_artifacts"
        }

    before = snapshot()
    original = UnitOfWork.commit
    with patch.object(UnitOfWork, "commit", autospec=True, side_effect=original) as commit:
        response = c.post(
            URL,
            json={"title": "  Software Resume  ", "external_url": "https://example.com/resume.pdf"},
        )
        assert response.status_code == 201, response.text
        assert commit.call_count == 1
    first = response.json()
    second = c.post(
        URL, json={"title": "Research Resume", "external_url": "https://example.com/research.pdf"}
    ).json()
    assert c.get(URL).json() == [first, second]
    assert c.get(URL + "/" + first["id"]).json() == first
    assert c.patch(URL + "/" + first["id"], json={}).json() == first
    edited = c.patch(
        URL + "/" + first["id"],
        json={"title": "Renamed", "external_url": "http://example.com/new.pdf"},
    ).json()
    assert edited["created_at"] == first["created_at"] and edited["title"] == "Renamed"
    assert c.get(URL).json() == [edited, second]
    assert c.delete(URL + "/" + first["id"]).status_code == 204
    assert c.get(URL).json() == [second]
    assert c.get(URL + "/" + first["id"]).status_code == 404
    assert snapshot() == before


@pytest.mark.parametrize(
    "bad",
    [
        {"title": ""},
        {"title": "  "},
        {"title": None},
        {"title": "x" * 151},
        {"external_url": ""},
        {"external_url": "relative.pdf"},
        {"external_url": "javascript:alert(1)"},
        {"external_url": "https://user:pass@example.com"},
        {"external_url": "https://example.com/a b"},
        {"external_url": "https://example.com:bad"},
        {"external_url": None},
        {"external_url": "file:///resume.pdf"},
        {"artifact_type": "COVER_LETTER"},
        {"artifact_type": None},
        {"user_id": str(uuid4())},
    ],
)
def test_invalid_create_update_preserve_existing(bad):
    c, _ = account()
    value = {"title": "Saved", "external_url": "https://example.com/resume.pdf"}
    saved = c.post(URL, json=value).json()
    assert c.post(URL, json={**value, **bad}).status_code == 422
    assert c.patch(URL + "/" + saved["id"], json=bad).status_code == 422
    assert c.get(URL).json() == [saved]


def test_ownership_auth_csrf_ids():
    a, _ = account()
    b, other = account()
    payload = {"title": "Private", "external_url": "https://example.com/private.pdf"}
    saved = a.post(URL, json=payload).json()
    path = URL + "/" + saved["id"]
    assert b.get(URL).json() == []
    for method in ["GET", "PATCH", "DELETE"]:
        assert (
            b.request(method, path, json=payload if method == "PATCH" else None).status_code == 404
        )
    for method, path2, value in [
        ("GET", URL, None),
        ("GET", path, None),
        ("POST", URL, payload),
        ("PATCH", path, payload),
        ("DELETE", path, None),
    ]:
        assert TestClient(app).request(method, path2, json=value).status_code == 401
        if method != "GET":
            assert (
                a.request(method, path2, json=value, headers={"X-CSRF-Token": "wrong"}).status_code
                == 403
            )
    assert a.get(URL + f"?user_id={other}").status_code == 422
    assert a.get(URL + "/invalid-id").status_code == 422
    assert a.get(URL).json() == [saved]
