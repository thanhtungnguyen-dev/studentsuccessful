"""Candidate-fit reads are deterministic, owner-scoped, and provenance preserving."""

import json
from datetime import date
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event, select

from backend.app.main import app
from backend.app.models.job import (
    JobEducationRequirement,
    JobEligibilityRequirement,
    JobSkillRequirement,
    NormalizedJob,
)
from backend.app.models.portfolio import Project, ProjectCustomSkill, ProjectSkill, UserCustomSkill
from backend.app.models.preference import UserPreferredSkill
from backend.app.models.profile import EmploymentRecord
from backend.app.models.resume import (
    Resume,
    ResumeEvidenceItem,
    ResumeEvidenceSkill,
    ResumeVersion,
    UserSkill,
)
from backend.app.models.taxonomy import Skill
from backend.tests.test_jobs import seed_job


def account():
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"fit-{uuid4().hex}@example.com", "password": "Fit-password-123!"},
    )
    assert response.status_code == 201
    return client, UUID(response.json()["user"]["id"])


def catalog(connection):
    skills = {name: uuid4() for name in ("Python", "AWS", "Docker", "Terraform")}
    connection.execute(
        Skill.__table__.insert(),
        [
            {"id": skill_id, "name": name, "slug": f"fit-{name.casefold()}", "category": "TECHNOLOGY"}
            for name, skill_id in skills.items()
        ],
    )
    return skills


def resume_source(connection, owner, skill_id):
    """Create retained evidence across historical and failed versions."""
    resume_id, historical, failed = uuid4(), uuid4(), uuid4()
    historical_item, failed_item = uuid4(), uuid4()
    connection.execute(Resume.__table__.insert(), {"id": resume_id, "user_id": owner, "title": "Private resume"})
    connection.execute(
        ResumeVersion.__table__.insert(),
        [
            {
                "id": historical, "resume_id": resume_id, "version_number": 1,
                "storage_key": "private/historical.pdf", "file_format": "PDF", "file_size_bytes": 1,
                "file_hash_sha256": "a" * 64, "parse_status": "PARSED_SUCCESS",
                "raw_extracted_text": "do not expose this resume text",
            },
            {
                "id": failed, "resume_id": resume_id, "version_number": 2,
                "storage_key": "private/failed.pdf", "file_format": "PDF", "file_size_bytes": 1,
                "file_hash_sha256": "b" * 64, "parse_status": "PARSE_FAILED",
                "raw_extracted_text": "also private",
            },
        ],
    )
    connection.execute(
        ResumeEvidenceItem.__table__.insert(),
        [
            {"id": historical_item, "resume_version_id": historical, "ordinal": 0, "category": "SKILLS", "bullet_text": "AWS"},
            {"id": failed_item, "resume_version_id": failed, "ordinal": 0, "category": "PROJECTS", "bullet_text": "AWS deployment"},
        ],
    )
    connection.execute(
        ResumeEvidenceSkill.__table__.insert(),
        [
            {"evidence_item_id": historical_item, "skill_id": skill_id, "parser_confidence": "0.90"},
            {"evidence_item_id": failed_item, "skill_id": skill_id, "parser_confidence": "0.60"},
        ],
    )
    return historical_item, failed_item


def project_source(connection, owner, skill_id):
    project_id = uuid4()
    connection.execute(
        Project.__table__.insert(),
        {"id": project_id, "user_id": owner, "title": "Catalog-linked project", "description": "Explicit only"},
    )
    connection.execute(ProjectSkill.__table__.insert(), {"project_id": project_id, "skill_id": skill_id})
    return project_id


def requirements(connection, job_id, skills):
    ids = {name: uuid4() for name in ("Python", "AWS", "Docker", "Terraform")}
    connection.execute(
        JobSkillRequirement.__table__.insert(),
        [
            {"id": ids["Python"], "job_id": job_id, "skill_id": skills["Python"], "importance": "REQUIRED", "description": "Python development"},
            {"id": ids["AWS"], "job_id": job_id, "skill_id": skills["AWS"], "importance": "PREFERRED", "description": "Cloud experience"},
            {"id": ids["Docker"], "job_id": job_id, "skill_id": skills["Docker"], "importance": "REQUIRED", "description": None},
            {"id": ids["Terraform"], "job_id": job_id, "skill_id": skills["Terraform"], "importance": "PREFERRED", "description": "Infrastructure as code"},
        ],
    )
    education_id, eligibility_id = uuid4(), uuid4()
    connection.execute(JobEducationRequirement.__table__.insert(), {
        "id": education_id, "job_id": job_id, "degree_level": "BS",
        "target_grad_start": date(2026, 5, 1), "target_grad_end": date(2027, 5, 1),
    })
    connection.execute(JobEligibilityRequirement.__table__.insert(), {
        "id": eligibility_id, "job_id": job_id, "requirement_type": "WORK_AUTHORIZATION",
        "value": "CA", "description": "Eligible to work in Canada", "source_evidence": "private ingestion detail",
    })
    return ids, education_id, eligibility_id


def test_fit_exactly_matches_owned_catalog_evidence_and_preserves_each_source(isolated_database):
    client, owner = account()
    skills = catalog(isolated_database)
    job_id = seed_job(isolated_database, title="Fit job", external_id="fit", posted_at=None)
    requirement_ids, education_id, eligibility_id = requirements(isolated_database, job_id, skills)
    user_skill_id = uuid4()
    isolated_database.execute(UserSkill.__table__.insert(), {
        "id": user_skill_id, "user_id": owner, "skill_id": skills["Python"], "source": "USER", "confirmed_by_user": True,
    })
    # An unconfirmed row is a fact record, never candidate evidence for this analysis.
    isolated_database.execute(UserSkill.__table__.insert(), {
        "id": uuid4(), "user_id": owner, "skill_id": skills["Docker"], "source": "IMPORT", "confirmed_by_user": False,
    })
    project_id = project_source(isolated_database, owner, skills["Terraform"])
    historical_item, failed_item = resume_source(isolated_database, owner, skills["AWS"])

    response = client.get(f"/api/v1/jobs/{job_id}/fit")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert {key: body[key] for key in ("job_id", "job_title", "company_name")} == {
        "job_id": str(job_id), "job_title": "Fit job", "company_name": "Fit job Company",
    }
    assert [item["requirement_id"] for item in body["matched"]] == [str(skills["AWS"]), str(skills["Python"]), str(skills["Terraform"])]
    assert [item["requirement_id"] for item in body["missing"]] == [str(skills["Docker"])]
    assert {item["requirement_id"] for item in body["unknown"]} == {str(education_id), str(eligibility_id)}

    matched = {item["name"]: item for item in body["matched"]}
    python_sources = matched["Python"]["sources"]
    assert [source["source_type"] for source in python_sources] == ["CONFIRMED_BY_USER"]
    assert python_sources[0]["source_id"] == str(user_skill_id)
    assert len(python_sources) == 1  # Confirmed user fact does not borrow unrelated project evidence.
    terraform_sources = matched["Terraform"]["sources"]
    assert terraform_sources == [{
        "source_type": "PROJECT", "source_id": str(project_id),
        "resume_id": None, "resume_title": None, "resume_version_id": None,
        "resume_version_number": None, "evidence_ordinal": None, "evidence_category": None,
        "evidence_section_header": None, "parser_confidence": None,
        "project_id": str(project_id), "project_title": "Catalog-linked project",
    }]
    aws_sources = matched["AWS"]["sources"]
    assert [source["source_type"] for source in aws_sources] == ["RESUME_EVIDENCE", "RESUME_EVIDENCE"]
    assert {source["source_id"] for source in aws_sources} == {str(historical_item), str(failed_item)}
    assert [source["resume_version_number"] for source in aws_sources] == [1, 2]
    assert all(item["category"] == "SKILL" for item in body["matched"] + body["missing"])
    assert all(item["sources"] == [] for item in body["missing"] + body["unknown"])
    assert all(item["category"] in {"EDUCATION", "ELIGIBILITY"} for item in body["unknown"])
    serialized = json.dumps(body)
    for forbidden_key in ("score", "recommendation", "user_id", "raw_extracted_text", "storage_key", "source_evidence"):
        assert f'"{forbidden_key}"' not in serialized
    for private_value in ("do not expose", "also private", "private/historical.pdf", "private ingestion detail"):
        assert private_value not in serialized
    assert body["limitations"]
    assert all(item["explanation"] and item["limitation"] for bucket in ("matched", "missing", "unknown") for item in body[bucket])
    assert body["missing"][0]["requirement_id"] == str(skills["Docker"])
    assert body["missing"][0]["importance"] == "REQUIRED"
    assert body["unknown"][0]["description"] or body["unknown"][1]["description"]


def test_fit_is_owner_scoped_read_only_and_deterministic(isolated_database):
    owner, owner_id = account()
    other, _ = account()
    skills = catalog(isolated_database)
    job_id = seed_job(isolated_database, title="Scoped fit", external_id="scoped-fit", posted_at=None)
    requirements(isolated_database, job_id, skills)
    isolated_database.execute(UserSkill.__table__.insert(), {
        "id": uuid4(), "user_id": owner_id, "skill_id": skills["Python"], "source": "USER", "confirmed_by_user": True,
    })
    project_source(isolated_database, owner_id, skills["Terraform"])
    resume_source(isolated_database, owner_id, skills["AWS"])
    tables = (
        UserSkill.__table__, Resume.__table__, ResumeVersion.__table__, ResumeEvidenceItem.__table__,
        ResumeEvidenceSkill.__table__, Project.__table__, ProjectSkill.__table__, JobSkillRequirement.__table__,
        NormalizedJob.__table__,
    )
    before = {table.name: list(isolated_database.execute(select(table)).mappings()) for table in tables}
    first = owner.get(f"/api/v1/jobs/{job_id}/fit")
    second = owner.get(f"/api/v1/jobs/{job_id}/fit")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert {table.name: list(isolated_database.execute(select(table)).mappings()) for table in tables} == before
    private = other.get(f"/api/v1/jobs/{job_id}/fit")
    assert private.status_code == 200
    assert private.json()["matched"] == []
    assert {item["requirement_id"] for item in private.json()["missing"]} == {str(skills[name]) for name in ("Python", "AWS", "Docker", "Terraform")}


def test_fit_handles_empty_requirements_and_rejects_unsafe_access(isolated_database):
    client, owner = account()
    job_id = seed_job(isolated_database, title="Empty fit", external_id="empty-fit", posted_at=None)
    response = client.get(f"/api/v1/jobs/{job_id}/fit")
    assert response.status_code == 200
    assert response.json()["matched"] == response.json()["missing"] == response.json()["unknown"] == []
    cases = (
        TestClient(app).get(f"/api/v1/jobs/{job_id}/fit"),
        client.get(f"/api/v1/jobs/{uuid4()}/fit"),
        client.get("/api/v1/jobs/not-a-uuid/fit"),
        client.get(f"/api/v1/jobs/{job_id}/fit", params={"user_id": owner}),
        client.get(f"/api/v1/jobs/{job_id}/fit", params={"anything": "else"}),
    )
    assert [response.status_code for response in cases] == [401, 404, 422, 422, 422]
    assert all(response.headers["cache-control"] == "no-store" for response in cases)
    inactive = seed_job(isolated_database, title="Inactive fit", external_id="inactive-fit", posted_at=None, active=False)
    hidden = client.get(f"/api/v1/jobs/{inactive}/fit")
    assert hidden.status_code == 404
    assert hidden.json()["code"] == "JOB_NOT_FOUND"


def test_fit_never_infers_capability_from_text_preferences_or_a_same_named_catalog_skill(isolated_database):
    client, owner = account()
    required_id, same_named_other_id = uuid4(), uuid4()
    isolated_database.execute(
        Skill.__table__.insert(),
        [
            {"id": required_id, "name": "Python", "slug": "fit-required-python", "category": "TECHNOLOGY"},
            {"id": same_named_other_id, "name": "Python", "slug": "fit-other-python", "category": "TECHNOLOGY"},
        ],
    )
    job_id = seed_job(isolated_database, title="Inference boundary", external_id="inference-boundary", posted_at=None)
    isolated_database.execute(JobSkillRequirement.__table__.insert(), {
        "id": uuid4(), "job_id": job_id, "skill_id": required_id, "importance": "REQUIRED", "description": "Python required",
    })
    # A same-looking catalog name still has a distinct canonical ID.
    isolated_database.execute(UserSkill.__table__.insert(), {
        "id": uuid4(), "user_id": owner, "skill_id": same_named_other_id, "source": "USER", "confirmed_by_user": True,
    })
    project_id = uuid4()
    isolated_database.execute(Project.__table__.insert(), {
        "id": project_id, "user_id": owner, "title": "Python in project title", "description": "Built Python services",
    })
    isolated_database.execute(ProjectCustomSkill.__table__.insert(), {
        "id": uuid4(), "project_id": project_id, "value": "Python", "normalized_value": "python",
    })
    isolated_database.execute(UserCustomSkill.__table__.insert(), {
        "id": uuid4(), "user_id": owner, "value": "Python", "normalized_value": "python",
    })
    isolated_database.execute(UserPreferredSkill.__table__.insert(), {"user_id": owner, "skill_id": required_id})
    isolated_database.execute(EmploymentRecord.__table__.insert(), {
        "id": uuid4(), "user_id": owner, "employer_name": "Python Co", "job_title": "Python Engineer",
        "start_date": date(2024, 1, 1), "end_date": date(2025, 1, 1), "description": "Used Python daily",
    })

    response = client.get(f"/api/v1/jobs/{job_id}/fit")
    assert response.status_code == 200, response.text
    assert response.json()["matched"] == []
    assert response.json()["missing"] == [{
        "category": "SKILL", "requirement_id": str(required_id), "name": "Python",
        "importance": "REQUIRED", "description": "Python required",
        "explanation": "No exact catalog skill reference is recorded in the candidate profile.",
        "limitation": "No recorded exact catalog-skill evidence was found; this is not an ability gap.",
        "sources": [],
    }]


def test_fit_keeps_confirmed_resume_and_project_sources_on_one_exact_requirement(isolated_database):
    client, owner = account()
    skills = catalog(isolated_database)
    job_id = seed_job(isolated_database, title="All sources", external_id="all-sources", posted_at=None)
    requirement_id = uuid4()
    isolated_database.execute(JobSkillRequirement.__table__.insert(), {
        "id": requirement_id, "job_id": job_id, "skill_id": skills["Python"], "importance": "REQUIRED", "description": None,
    })
    confirmed_id = uuid4()
    isolated_database.execute(UserSkill.__table__.insert(), {
        "id": confirmed_id, "user_id": owner, "skill_id": skills["Python"], "source": "USER", "confirmed_by_user": True,
    })
    project_id = project_source(isolated_database, owner, skills["Python"])
    historical_item, failed_item = resume_source(isolated_database, owner, skills["Python"])

    response = client.get(f"/api/v1/jobs/{job_id}/fit")
    assert response.status_code == 200, response.text
    matched = response.json()["matched"]
    assert len(matched) == 1
    assert matched[0]["requirement_id"] == str(skills["Python"])
    sources = matched[0]["sources"]
    assert [source["source_type"] for source in sources] == [
        "CONFIRMED_BY_USER", "RESUME_EVIDENCE", "RESUME_EVIDENCE", "PROJECT",
    ]
    assert {source["source_id"] for source in sources} == {
        str(confirmed_id), str(historical_item), str(failed_item), str(project_id),
    }


def test_fit_uses_a_bounded_read_query_set(isolated_database):
    client, owner = account()
    skills = catalog(isolated_database)
    job_id = seed_job(isolated_database, title="Bounded fit", external_id="bounded-fit", posted_at=None)
    requirements(isolated_database, job_id, skills)
    isolated_database.execute(UserSkill.__table__.insert(), {
        "id": uuid4(), "user_id": owner, "skill_id": skills["Python"], "source": "USER", "confirmed_by_user": True,
    })
    statements: list[str] = []

    def capture(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(isolated_database, "before_cursor_execute", capture)
    try:
        response = client.get(f"/api/v1/jobs/{job_id}/fit")
    finally:
        event.remove(isolated_database, "before_cursor_execute", capture)
    assert response.status_code == 200
    reads = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]
    # The endpoint performs a bounded fixed set of catalog, owner-evidence, and session reads.
    assert len(reads) <= 10
    assert not [statement for statement in statements if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
