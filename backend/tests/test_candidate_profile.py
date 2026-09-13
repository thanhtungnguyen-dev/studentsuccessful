"""Candidate-profile aggregation preserves ownership and source provenance."""

import json
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from backend.app.main import app
from backend.app.models.resume import (
    Resume,
    ResumeEvidenceItem,
    ResumeEvidenceSkill,
    ResumeVersion,
    UserSkill,
)
from backend.app.models.taxonomy import Skill

URL = "/api/v1/profile/candidate"


def account():
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"candidate-{uuid4().hex}@example.com", "password": "Candidate-password-123!"},
    )
    assert response.status_code == 201
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client, UUID(response.json()["user"]["id"])


def catalog(isolated_database):
    skills = {
        name: uuid4() for name in ("Docker", "Python", "Terraform")
    }
    isolated_database.execute(
        Skill.__table__.insert(),
        [
            {"id": skill_id, "name": name, "slug": name.casefold(), "category": "TECHNOLOGY"}
            for name, skill_id in skills.items()
        ],
    )
    return skills


def insert_resume_evidence(isolated_database, owner, skills, *, title="Backend Resume", status="PARSED_SUCCESS"):
    resume_id, first_version, second_version = uuid4(), uuid4(), uuid4()
    first_item, second_item, docker_item = uuid4(), uuid4(), uuid4()
    isolated_database.execute(
        Resume.__table__.insert(), {"id": resume_id, "user_id": owner, "title": title}
    )
    isolated_database.execute(
        ResumeVersion.__table__.insert(),
        [
            {
                "id": first_version,
                "resume_id": resume_id,
                "version_number": 1,
                "storage_key": "private/v1.pdf",
                "file_format": "PDF",
                "file_size_bytes": 1,
                "file_hash_sha256": "a" * 64,
                "parse_status": status,
                "raw_extracted_text": "private extracted text must never be returned",
            },
            {
                "id": second_version,
                "resume_id": resume_id,
                "version_number": 2,
                "storage_key": "private/v2.pdf",
                "file_format": "PDF",
                "file_size_bytes": 1,
                "file_hash_sha256": "b" * 64,
                "parse_status": status,
                "raw_extracted_text": "also private",
            },
        ],
    )
    isolated_database.execute(
        ResumeEvidenceItem.__table__.insert(),
        [
            {
                "id": first_item,
                "resume_version_id": first_version,
                "ordinal": 0,
                "category": "SKILLS",
                "section_header": "Skills",
                "bullet_text": "Python",
            },
            {
                "id": second_item,
                "resume_version_id": second_version,
                "ordinal": 1,
                "category": "PROJECTS",
                "section_header": "Projects",
                "bullet_text": "Python deployment",
            },
            {
                "id": docker_item,
                "resume_version_id": second_version,
                "ordinal": 2,
                "category": "SKILLS",
                "section_header": "Skills",
                "bullet_text": "Docker",
            },
        ],
    )
    isolated_database.execute(
        ResumeEvidenceSkill.__table__.insert(),
        [
            {"evidence_item_id": first_item, "skill_id": skills["Python"], "parser_confidence": Decimal("1.00")},
            {"evidence_item_id": second_item, "skill_id": skills["Python"], "parser_confidence": Decimal("0.80")},
            {"evidence_item_id": docker_item, "skill_id": skills["Docker"], "parser_confidence": Decimal("0.90")},
        ],
    )
    return {"resume": resume_id, "versions": (first_version, second_version), "items": (first_item, second_item, docker_item)}


def test_empty_candidate_profile_is_read_only_and_has_explicit_fact_provenance():
    client, _ = account()
    response = client.get(URL)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "facts_source": "ADDED_BY_USER",
        "profile": None,
        "education": [],
        "employment": [],
        "work_authorizations": [],
        "preferences": {
            "role_ids": [], "industry_ids": [], "location_ids": [], "company_ids": [],
            "skill_ids": [], "work_modes": [], "employment_types": [], "custom_values": [],
        },
        "projects": [],
        "skills": [],
        "custom_skills": [],
        "resume_evidence": [],
    }


def test_profile_aggregates_explicit_facts_and_reconciles_exact_catalog_sources(isolated_database):
    client, owner = account()
    skills = catalog(isolated_database)
    profile = client.patch(
        "/api/v1/profile",
        json={"legal_first_name": "Ada", "legal_last_name": "Lovelace", "preferred_name": "Ada"},
    )
    assert profile.status_code == 200
    education = client.post(
        "/api/v1/profile/education",
        json={
            "institution_name": "Example University", "degree_level": "BS", "major": "Computer Science",
            "study_year": "YEAR_4", "start_date": "2022-09-01", "expected_grad_month": 5,
            "expected_grad_year": 2026, "is_primary": True,
        },
    )
    employment = client.post(
        "/api/v1/profile/employment",
        json={"employer_name": "Example Co", "job_title": "Intern", "start_date": "2025-05-01", "end_date": "2025-08-01"},
    )
    authorization = client.post(
        "/api/v1/profile/work-authorizations",
        json={"country_code": "CA", "authorization_status": "STUDENT_WORK_AUTHORIZATION"},
    )
    preferences = client.put(
        "/api/v1/preferences",
        json={"skill_ids": [str(skills["Terraform"])], "work_modes": ["REMOTE"]},
    )
    assert all(response.status_code in {200, 201} for response in (education, employment, authorization, preferences))
    assert client.put(
        "/api/v1/profile/skills",
        json={"skill_ids": [str(skills["Python"])], "custom_values": ["Terminal workflows"]},
    ).status_code == 200
    project = client.post(
        "/api/v1/profile/projects",
        json={
            "title": "Cloud deployment", "description": "Explicit project description",
            "technologies": {"skill_ids": [str(skills["Python"]), str(skills["Docker"])], "custom_values": ["Terminal workflows"]},
        },
    )
    assert project.status_code == 201
    source_ids = insert_resume_evidence(isolated_database, owner, skills)

    response = client.get(URL)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["profile"] == profile.json()
    assert [row["id"] for row in body["education"]] == [education.json()["id"]]
    assert [row["id"] for row in body["employment"]] == [employment.json()["id"]]
    assert [row["id"] for row in body["work_authorizations"]] == [authorization.json()["id"]]
    assert body["preferences"] == preferences.json()
    assert [row["id"] for row in body["projects"]] == [project.json()["id"]]

    by_name = {row["name"]: row for row in body["skills"]}
    assert list(by_name) == ["Docker", "Python"]
    assert [source["source_type"] for source in by_name["Python"]["sources"]] == [
        "CONFIRMED_BY_USER", "RESUME_EVIDENCE", "RESUME_EVIDENCE", "PROJECT"
    ]
    evidence_sources = by_name["Python"]["sources"][1:3]
    assert [(source["resume_version_number"], source["evidence_ordinal"]) for source in evidence_sources] == [(1, 0), (2, 1)]
    assert {source["source_id"] for source in evidence_sources} == {str(source_ids["items"][0]), str(source_ids["items"][1])}
    assert by_name["Python"]["sources"][3] == {
        "source_type": "PROJECT", "source_id": project.json()["id"],
        "resume_id": None, "resume_title": None, "resume_version_id": None,
        "resume_version_number": None, "evidence_ordinal": None, "evidence_category": None,
        "evidence_section_header": None, "parser_confidence": None,
        "project_id": project.json()["id"], "project_title": "Cloud deployment",
    }
    assert [source["source_type"] for source in by_name["Docker"]["sources"]] == ["RESUME_EVIDENCE", "PROJECT"]
    assert body["custom_skills"] == [{
        "name": "Terminal workflows",
        "sources": [
            {"source_type": "CONFIRMED_BY_USER", "source_id": body["custom_skills"][0]["sources"][0]["source_id"], "project_id": None, "project_title": None},
            {"source_type": "PROJECT", "source_id": body["custom_skills"][0]["sources"][1]["source_id"], "project_id": project.json()["id"], "project_title": "Cloud deployment"},
        ],
    }]
    assert [(item["resume_version_number"], item["ordinal"]) for item in body["resume_evidence"]] == [(1, 0), (2, 1), (2, 2)]
    assert body["resume_evidence"][0]["recognized_skills"] == [{
        "skill_id": str(skills["Python"]), "name": "Python", "parser_confidence": "1.00"
    }]
    serialized = json.dumps(body)
    for private_value in ("raw_extracted_text", "storage_key", "file_hash_sha256", "private extracted text"):
        assert private_value not in serialized
    assert "Terraform" not in by_name  # Preference interest never becomes a capability claim.


def test_candidate_profile_rejects_owner_injection_and_never_leaks_other_user_data(isolated_database):
    owner, owner_id = account()
    other, _ = account()
    skills = catalog(isolated_database)
    insert_resume_evidence(isolated_database, owner_id, skills, title="Owner Resume")
    assert owner.get(URL).json()["resume_evidence"][0]["resume_title"] == "Owner Resume"
    private = other.get(URL)
    assert private.status_code == 200 and private.json()["resume_evidence"] == []
    rejected = other.get(f"{URL}?user_id={owner_id}")
    assert rejected.status_code == 422
    assert rejected.headers["cache-control"] == "no-store"
    unauthenticated = TestClient(app).get(URL)
    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["cache-control"] == "no-store"


def test_deleted_resume_evidence_disappears_without_affecting_confirmed_skills(isolated_database):
    client, owner = account()
    skills = catalog(isolated_database)
    isolated_database.execute(
        UserSkill.__table__.insert(),
        {"user_id": owner, "skill_id": skills["Python"], "source": "USER", "confirmed_by_user": True},
    )
    sources = insert_resume_evidence(isolated_database, owner, skills, status="PARSE_FAILED")
    before = client.get(URL).json()
    python = next(row for row in before["skills"] if row["name"] == "Python")
    assert [source["source_type"] for source in python["sources"]] == [
        "CONFIRMED_BY_USER", "RESUME_EVIDENCE", "RESUME_EVIDENCE"
    ]
    assert len(before["resume_evidence"]) == 3  # Retained successful evidence remains visible after a failed retry.
    isolated_database.execute(delete(ResumeVersion).where(ResumeVersion.id == sources["versions"][1]))
    after = client.get(URL).json()
    python = next(row for row in after["skills"] if row["name"] == "Python")
    assert [source["source_type"] for source in python["sources"]] == ["CONFIRMED_BY_USER", "RESUME_EVIDENCE"]
    assert [(item["resume_version_number"], item["ordinal"]) for item in after["resume_evidence"]] == [(1, 0)]
    assert isolated_database.execute(
        select(UserSkill.id).where(UserSkill.user_id == owner, UserSkill.skill_id == skills["Python"])
    ).scalar_one()
