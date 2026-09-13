"""Additional security regressions for the read-only candidate-profile projection."""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event, select

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.main import app
from backend.app.models.portfolio import Project, ProjectCustomSkill, ProjectSkill, UserCustomSkill
from backend.app.models.preference import (
    CareerPreference,
    CareerPreferenceCustomValue,
    UserPreferredCompany,
    UserPreferredIndustry,
    UserPreferredLocation,
    UserPreferredRole,
    UserPreferredSkill,
)
from backend.app.models.profile import (
    ApplicationProfile,
    EducationRecord,
    EmploymentRecord,
    WorkAuthorization,
)
from backend.app.models.resume import (
    Resume,
    ResumeEvidenceItem,
    ResumeEvidenceSkill,
    ResumeVersion,
    UserSkill,
)
from backend.app.models.taxonomy import Skill

URL = "/api/v1/profile/candidate"


def account() -> tuple[TestClient, UUID]:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"candidate-security-{uuid4().hex}@example.com", "password": "Password123!"},
    )
    assert response.status_code == 201
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client, UUID(response.json()["user"]["id"])


def add_catalog_skill(connection, name: str = "Python") -> UUID:
    skill_id = uuid4()
    connection.execute(
        Skill.__table__.insert(),
        {"id": skill_id, "name": name, "slug": name.casefold(), "category": "TECHNOLOGY"},
    )
    return skill_id


def add_resume_evidence(connection, owner: UUID, skill_id: UUID, sentinel: str) -> dict[str, UUID]:
    resume_id, version_id, evidence_id = uuid4(), uuid4(), uuid4()
    connection.execute(
        Resume.__table__.insert(),
        {"id": resume_id, "user_id": owner, "title": f"{sentinel} Resume"},
    )
    connection.execute(
        ResumeVersion.__table__.insert(),
        {
            "id": version_id,
            "resume_id": resume_id,
            "version_number": 1,
            "storage_key": f"private/{sentinel}.pdf",
            "file_format": "PDF",
            "file_size_bytes": 1,
            "file_hash_sha256": "a" * 64,
            "parse_status": "PARSED_SUCCESS",
            "raw_extracted_text": f"{sentinel} private extracted text",
        },
    )
    connection.execute(
        ResumeEvidenceItem.__table__.insert(),
        {
            "id": evidence_id,
            "resume_version_id": version_id,
            "ordinal": 0,
            "category": "SKILLS",
            "section_header": f"{sentinel} Skills",
            "bullet_text": f"{sentinel} Python evidence",
        },
    )
    connection.execute(
        ResumeEvidenceSkill.__table__.insert(),
        {"evidence_item_id": evidence_id, "skill_id": skill_id, "parser_confidence": Decimal("0.75")},
    )
    return {"resume": resume_id, "version": version_id, "evidence": evidence_id}


def seed_factual_sources(client: TestClient, owner: UUID, skill_id: UUID, sentinel: str, connection) -> dict:
    responses = [
        client.patch(
            "/api/v1/profile",
            json={"legal_first_name": f"{sentinel}First", "legal_last_name": f"{sentinel}Last"},
        ),
        client.post(
            "/api/v1/profile/education",
            json={
                "institution_name": f"{sentinel} University",
                "degree_level": "BS",
                "major": f"{sentinel} Studies",
                "study_year": "YEAR_4",
                "start_date": "2022-09-01",
                "expected_grad_month": 5,
                "expected_grad_year": 2026,
            },
        ),
        client.post(
            "/api/v1/profile/employment",
            json={
                "employer_name": f"{sentinel} Employer",
                "job_title": f"{sentinel} Engineer",
                "start_date": "2024-01-01",
                "end_date": "2024-06-01",
                "description": f"{sentinel} employment description",
            },
        ),
        client.post(
            "/api/v1/profile/work-authorizations",
            json={
                "country_code": "CA",
                "authorization_status": "STUDENT_WORK_AUTHORIZATION",
                "notes": f"{sentinel} authorization note",
            },
        ),
        client.put(
            "/api/v1/preferences",
            json={
                "work_modes": ["REMOTE"],
                "custom_values": [{"preference_type": "ROLE", "value": f"{sentinel} preference"}],
            },
        ),
        client.put(
            "/api/v1/profile/skills",
            json={"skill_ids": [str(skill_id)], "custom_values": [f"{sentinel} custom skill"]},
        ),
    ]
    assert all(response.status_code in {200, 201} for response in responses)
    project = client.post(
        "/api/v1/profile/projects",
        json={
            "title": f"{sentinel} Project",
            "description": f"{sentinel} project description",
            "technologies": {
                "skill_ids": [str(skill_id)],
                "custom_values": [f"{sentinel} project technology"],
            },
        },
    )
    assert project.status_code == 201
    return {"project": project.json(), "resume": add_resume_evidence(connection, owner, skill_id, sentinel)}


SOURCE_TABLES = (
    ApplicationProfile.__table__,
    EducationRecord.__table__,
    EmploymentRecord.__table__,
    WorkAuthorization.__table__,
    CareerPreference.__table__,
    CareerPreferenceCustomValue.__table__,
    UserPreferredRole.__table__,
    UserPreferredIndustry.__table__,
    UserPreferredLocation.__table__,
    UserPreferredCompany.__table__,
    UserPreferredSkill.__table__,
    UserSkill.__table__,
    UserCustomSkill.__table__,
    Project.__table__,
    ProjectSkill.__table__,
    ProjectCustomSkill.__table__,
    Resume.__table__,
    ResumeVersion.__table__,
    ResumeEvidenceItem.__table__,
    ResumeEvidenceSkill.__table__,
)


def source_snapshot(connection) -> dict[str, list[dict]]:
    return {
        table.name: [dict(row) for row in connection.execute(select(table)).mappings()]
        for table in SOURCE_TABLES
    }


def test_candidate_get_has_no_commits_or_database_writes_after_full_source_seed(
    isolated_database,
):
    client, owner = account()
    skill_id = add_catalog_skill(isolated_database)
    seed_factual_sources(client, owner, skill_id, "NoWriteSentinel", isolated_database)
    before = source_snapshot(isolated_database)
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(isolated_database, "before_cursor_execute", capture)
    try:
        with patch.object(
            UnitOfWork,
            "commit",
            autospec=True,
            side_effect=AssertionError("candidate GET must not commit"),
        ) as commit:
            first = client.get(URL)
            second = client.get(URL)
        assert first.status_code == second.status_code == 200
        assert first.headers["cache-control"] == second.headers["cache-control"] == "no-store"
        assert first.json() == second.json()
        commit.assert_not_called()
    finally:
        event.remove(isolated_database, "before_cursor_execute", capture)

    assert source_snapshot(isolated_database) == before
    assert not any(
        statement.lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE "))
        for statement in statements
    )


def test_candidate_profile_keeps_all_factual_sentinels_owner_scoped(isolated_database):
    owner_client, owner = account()
    peer_client, peer = account()
    skill_id = add_catalog_skill(isolated_database)
    seed_factual_sources(owner_client, owner, skill_id, "OwnerSentinel", isolated_database)
    seed_factual_sources(peer_client, peer, skill_id, "PeerSentinel", isolated_database)

    owner_response = owner_client.get(URL)
    peer_response = peer_client.get(URL)
    assert owner_response.status_code == peer_response.status_code == 200
    owner_body = json.dumps(owner_response.json())
    peer_body = json.dumps(peer_response.json())

    assert "OwnerSentinel" in owner_body and "PeerSentinel" not in owner_body
    assert "PeerSentinel" in peer_body and "OwnerSentinel" not in peer_body
    assert owner_response.json()["profile"]["legal_first_name"] == "OwnerSentinelFirst"
    assert owner_response.json()["education"][0]["institution_name"] == "OwnerSentinel University"
    assert owner_response.json()["employment"][0]["employer_name"] == "OwnerSentinel Employer"
    assert owner_response.json()["work_authorizations"][0]["notes"] == "OwnerSentinel authorization note"
    assert owner_response.json()["projects"][0]["title"] == "OwnerSentinel Project"
    assert owner_response.json()["resume_evidence"][0]["resume_title"] == "OwnerSentinel Resume"


def test_deleting_a_project_removes_only_its_candidate_sources(isolated_database):
    client, owner = account()
    skill_id = add_catalog_skill(isolated_database)
    assert client.put("/api/v1/profile/skills", json={"skill_ids": [str(skill_id)]}).status_code == 200
    resume = add_resume_evidence(isolated_database, owner, skill_id, "PreservedResume")
    project = client.post(
        "/api/v1/profile/projects",
        json={
            "title": "Disposable Project",
            "technologies": {"skill_ids": [str(skill_id)], "custom_values": ["Project only tooling"]},
        },
    )
    assert project.status_code == 201
    before = client.get(URL).json()
    skill = next(row for row in before["skills"] if row["skill_id"] == str(skill_id))
    assert [source["source_type"] for source in skill["sources"]] == [
        "CONFIRMED_BY_USER",
        "RESUME_EVIDENCE",
        "PROJECT",
    ]
    assert any(row["name"] == "Project only tooling" for row in before["custom_skills"])

    deleted = client.delete(f"/api/v1/profile/projects/{project.json()['id']}")
    assert deleted.status_code == 204
    after = client.get(URL).json()
    skill = next(row for row in after["skills"] if row["skill_id"] == str(skill_id))
    assert [source["source_type"] for source in skill["sources"]] == [
        "CONFIRMED_BY_USER",
        "RESUME_EVIDENCE",
    ]
    assert after["resume_evidence"][0]["evidence_item_id"] == str(resume["evidence"])
    assert all(row["name"] != "Project only tooling" for row in after["custom_skills"])
    assert isolated_database.execute(
        select(UserSkill.id).where(UserSkill.user_id == owner, UserSkill.skill_id == skill_id)
    ).scalar_one()
    assert isolated_database.execute(
        select(ResumeEvidenceItem.id).where(ResumeEvidenceItem.id == resume["evidence"])
    ).scalar_one() == resume["evidence"]


def test_custom_sources_group_deterministically_without_promoting_project_only_values(isolated_database):
    client, owner = account()
    assert client.put(
        "/api/v1/profile/skills", json={"custom_values": ["Shared tooling"]}
    ).status_code == 200
    project = client.post(
        "/api/v1/profile/projects",
        json={
            "title": "Alpha Project",
            "technologies": {"custom_values": [" shared tooling ", "Project only tooling"]},
        },
    )
    assert project.status_code == 201

    first = client.get(URL)
    second = client.get(URL)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    body = first.json()
    assert body["skills"] == []
    by_name = {row["name"]: row for row in body["custom_skills"]}
    assert [source["source_type"] for source in by_name["Shared tooling"]["sources"]] == [
        "CONFIRMED_BY_USER",
        "PROJECT",
    ]
    project_only = by_name["Project only tooling"]
    assert [source["source_type"] for source in project_only["sources"]] == ["PROJECT"]
    assert project_only["sources"][0]["project_id"] == project.json()["id"]
    assert isolated_database.execute(select(UserSkill.id).where(UserSkill.user_id == owner)).all() == []
    assert isolated_database.execute(
        select(UserCustomSkill.id).where(UserCustomSkill.user_id == owner)
    ).scalar_one()


def test_candidate_unauthenticated_response_is_private_and_not_cacheable():
    response = TestClient(app).get(URL)
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
    assert response.headers["cache-control"] == "no-store"
