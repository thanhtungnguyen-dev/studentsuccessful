"""Exact-evidence, selected-version skill gap analysis reads."""

import json
from datetime import date
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

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
        json={"email": f"gaps-{uuid4().hex}@example.com", "password": "Gaps-password-123!"},
    )
    assert response.status_code == 201
    return client, UUID(response.json()["user"]["id"])


def catalog(connection):
    skills = {name: uuid4() for name in ("Python", "Docker", "AWS", "Terraform", "Kubernetes")}
    connection.execute(
        Skill.__table__.insert(),
        [
            {
                "id": skill_id,
                "name": name,
                "slug": f"gaps-{name.casefold()}",
                "category": "TECHNOLOGY",
            }
            for name, skill_id in skills.items()
        ],
    )
    return skills


def job_requirements(connection, job_id, skills):
    connection.execute(
        JobSkillRequirement.__table__.insert(),
        [
            {
                "id": uuid4(),
                "job_id": job_id,
                "skill_id": skills[name],
                "importance": "REQUIRED" if name in {"Python", "Docker"} else "PREFERRED",
                "description": f"{name} requirement",
            }
            for name in ("Python", "Docker", "AWS", "Terraform", "Kubernetes")
        ],
    )
    education_id, eligibility_id = uuid4(), uuid4()
    connection.execute(
        JobEducationRequirement.__table__.insert(),
        {
            "id": education_id,
            "job_id": job_id,
            "degree_level": "BS",
            "target_grad_start": date(2026, 5, 1),
            "target_grad_end": date(2027, 5, 1),
        },
    )
    connection.execute(
        JobEligibilityRequirement.__table__.insert(),
        {
            "id": eligibility_id,
            "job_id": job_id,
            "requirement_type": "WORK_AUTHORIZATION",
            "value": "CA",
            "description": "Eligible to work in Canada",
            "source_evidence": "private ingestion source",
        },
    )
    return education_id, eligibility_id


def resume_versions(connection, owner, selected_skill_id, other_version_skill_id):
    resume_id, selected_id, other_id = uuid4(), uuid4(), uuid4()
    selected_item, other_item = uuid4(), uuid4()
    connection.execute(
        Resume.__table__.insert(),
        {"id": resume_id, "user_id": owner, "title": "Targeted resume"},
    )
    connection.execute(
        ResumeVersion.__table__.insert(),
        [
            {
                "id": selected_id,
                "resume_id": resume_id,
                "version_number": 1,
                "storage_key": "private/selected.pdf",
                "file_format": "PDF",
                "file_size_bytes": 1,
                "file_hash_sha256": "a" * 64,
                "parse_status": "PARSED_SUCCESS",
                "raw_extracted_text": "Unlinked raw text says Terraform and must not count.",
            },
            {
                "id": other_id,
                "resume_id": resume_id,
                "version_number": 2,
                "storage_key": "private/other.pdf",
                "file_format": "PDF",
                "file_size_bytes": 1,
                "file_hash_sha256": "b" * 64,
                "parse_status": "PARSED_SUCCESS",
                "raw_extracted_text": "Private alternate text",
            },
        ],
    )
    connection.execute(
        ResumeEvidenceItem.__table__.insert(),
        [
            {
                "id": selected_item,
                "resume_version_id": selected_id,
                "ordinal": 0,
                "category": "SKILLS",
                "section_header": "Skills",
                "bullet_text": "Python",
            },
            {
                "id": other_item,
                "resume_version_id": other_id,
                "ordinal": 0,
                "category": "SKILLS",
                "section_header": "Skills",
                "bullet_text": "Terraform",
            },
        ],
    )
    connection.execute(
        ResumeEvidenceSkill.__table__.insert(),
        [
            {
                "evidence_item_id": selected_item,
                "skill_id": selected_skill_id,
                "parser_confidence": "0.95",
            },
            {
                "evidence_item_id": other_item,
                "skill_id": other_version_skill_id,
                "parser_confidence": "0.90",
            },
        ],
    )
    return resume_id, selected_id, other_id, selected_item, other_item


def add_project_technology(connection, owner, skill_id):
    project_id = uuid4()
    connection.execute(
        Project.__table__.insert(),
        {
            "id": project_id,
            "user_id": owner,
            "title": "Catalog technology project",
            "description": "Free text is not used for gap analysis.",
        },
    )
    connection.execute(
        ProjectSkill.__table__.insert(),
        {"project_id": project_id, "skill_id": skill_id},
    )
    return project_id


def test_skill_gap_classifies_exact_sources_and_selected_version_provenance(isolated_database):
    client, owner = account()
    skills = catalog(isolated_database)
    job_id = seed_job(isolated_database, title="Gap job", external_id="gap-job", posted_at=None)
    education_id, eligibility_id = job_requirements(isolated_database, job_id, skills)
    resume_id, selected_id, other_id, selected_item, other_item = resume_versions(
        isolated_database, owner, skills["Python"], skills["Terraform"]
    )
    confirmed_id = uuid4()
    isolated_database.execute(
        UserSkill.__table__.insert(),
        {
            "id": confirmed_id,
            "user_id": owner,
            "skill_id": skills["Docker"],
            "source": "USER",
            "confirmed_by_user": True,
        },
    )
    project_id = add_project_technology(isolated_database, owner, skills["AWS"])

    response = client.get(f"/api/v1/jobs/{job_id}/gaps", params={"resume_version_id": selected_id})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert {
        key: body[key]
        for key in (
            "job_id",
            "job_title",
            "company_name",
            "resume_id",
            "resume_title",
            "resume_version_id",
            "resume_version_number",
        )
    } == {
        "job_id": str(job_id),
        "job_title": "Gap job",
        "company_name": "Gap job Company",
        "resume_id": str(resume_id),
        "resume_title": "Targeted resume",
        "resume_version_id": str(selected_id),
        "resume_version_number": 1,
    }
    assert [item["name"] for item in body["covered"]] == ["Python"]
    assert [item["name"] for item in body["resume_presentation_gaps"]] == [
        "AWS",
        "Docker",
        "Terraform",
    ]
    assert [item["name"] for item in body["candidate_evidence_gaps"]] == ["Kubernetes"]
    assert {item["requirement_id"] for item in body["unknown"]} == {
        str(education_id),
        str(eligibility_id),
    }
    assert [item["classification"] for item in body["covered"]] == ["COVERED"]
    assert all(
        item["classification"] == "RESUME_PRESENTATION_GAP"
        for item in body["resume_presentation_gaps"]
    )
    assert body["candidate_evidence_gaps"][0]["classification"] == "CANDIDATE_EVIDENCE_GAP"
    assert all(item["classification"] == "UNKNOWN_UNASSESSED" for item in body["unknown"])

    covered_source = body["covered"][0]["sources"]
    assert covered_source[0]["source_type"] == "RESUME_EVIDENCE"
    assert covered_source[0]["source_id"] == str(selected_item)
    assert covered_source[0]["resume_version_id"] == str(selected_id)
    presentation = {item["name"]: item for item in body["resume_presentation_gaps"]}
    assert presentation["Docker"]["sources"][0]["source_type"] == "CONFIRMED_BY_USER"
    assert presentation["Docker"]["sources"][0]["source_id"] == str(confirmed_id)
    assert presentation["AWS"]["sources"][0]["source_type"] == "PROJECT"
    assert presentation["AWS"]["sources"][0]["source_id"] == str(project_id)
    assert presentation["AWS"]["sources"][0]["project_title"] == "Catalog technology project"
    terraform_source = presentation["Terraform"]["sources"]
    assert terraform_source[0]["source_type"] == "RESUME_EVIDENCE"
    assert terraform_source[0]["source_id"] == str(other_item)
    assert terraform_source[0]["resume_version_id"] == str(other_id)
    assert terraform_source[0]["resume_version_number"] == 2
    assert "Terraform" not in [item["name"] for item in body["covered"]]
    assert body["candidate_evidence_gaps"][0]["sources"] == []
    assert "No recorded supporting evidence for Kubernetes." == body["candidate_evidence_gaps"][0]["explanation"]
    serialized = json.dumps(body)
    for forbidden in (
        "user_id",
        "storage_key",
        "file_hash_sha256",
        "file_size_bytes",
        "raw_extracted_text",
        "private/selected.pdf",
        "private ingestion source",
    ):
        assert forbidden not in serialized


def test_skill_gap_is_owner_scoped_read_only_and_handles_missing_records_safely(isolated_database):
    client, owner = account()
    other, _ = account()
    skills = catalog(isolated_database)
    job_id = seed_job(
        isolated_database, title="Private gap", external_id="private-gap", posted_at=None
    )
    job_requirements(isolated_database, job_id, skills)
    _, selected_id, _, _, _ = resume_versions(
        isolated_database, owner, skills["Python"], skills["Terraform"]
    )
    tables = (
        Resume.__table__,
        ResumeVersion.__table__,
        ResumeEvidenceItem.__table__,
        ResumeEvidenceSkill.__table__,
        UserSkill.__table__,
        Project.__table__,
        ProjectSkill.__table__,
        JobSkillRequirement.__table__,
        NormalizedJob.__table__,
    )
    before = {table.name: list(isolated_database.execute(select(table)).mappings()) for table in tables}
    first = client.get(f"/api/v1/jobs/{job_id}/gaps", params={"resume_version_id": selected_id})
    second = client.get(f"/api/v1/jobs/{job_id}/gaps", params={"resume_version_id": selected_id})
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert {table.name: list(isolated_database.execute(select(table)).mappings()) for table in tables} == before

    inaccessible = other.get(f"/api/v1/jobs/{job_id}/gaps", params={"resume_version_id": selected_id})
    missing_version = client.get(f"/api/v1/jobs/{job_id}/gaps", params={"resume_version_id": uuid4()})
    missing_job = client.get(f"/api/v1/jobs/{uuid4()}/gaps", params={"resume_version_id": selected_id})
    unauthenticated = TestClient(app).get(
        f"/api/v1/jobs/{job_id}/gaps", params={"resume_version_id": selected_id}
    )
    write_attempt = client.post(f"/api/v1/jobs/{job_id}/gaps", params={"resume_version_id": selected_id})
    assert [
        response.status_code
        for response in (inaccessible, missing_version, missing_job, unauthenticated, write_attempt)
    ] == [404, 404, 404, 401, 405]
    assert inaccessible.json()["code"] == missing_version.json()["code"] == "RESUME_VERSION_NOT_FOUND"
    assert missing_job.json()["code"] == "JOB_NOT_FOUND"
    assert all(
        response.headers["cache-control"] == "no-store"
        for response in (inaccessible, missing_version, missing_job, unauthenticated, write_attempt)
    )


def test_skill_gap_rejects_unsafe_or_ambiguous_query_inputs(isolated_database):
    client, owner = account()
    skills = catalog(isolated_database)
    job_id = seed_job(isolated_database, title="Query gap", external_id="query-gap", posted_at=None)
    job_requirements(isolated_database, job_id, skills)
    _, selected_id, _, _, _ = resume_versions(
        isolated_database, owner, skills["Python"], skills["Terraform"]
    )
    cases = (
        client.get(f"/api/v1/jobs/{job_id}/gaps"),
        client.get(
            f"/api/v1/jobs/{job_id}/gaps",
            params=[("resume_version_id", str(selected_id)), ("resume_version_id", str(uuid4()))],
        ),
        client.get(
            f"/api/v1/jobs/{job_id}/gaps",
            params={"resume_version_id": selected_id, "user_id": owner},
        ),
        client.get(f"/api/v1/jobs/{job_id}/fit", params={"resume_version_id": selected_id}),
    )
    assert [response.status_code for response in cases] == [422, 422, 422, 422]
    assert all(response.headers["cache-control"] == "no-store" for response in cases)


def test_skill_gap_never_infers_from_raw_text_preferences_or_free_text(isolated_database):
    client, owner = account()
    required_id, same_named_id = uuid4(), uuid4()
    isolated_database.execute(
        Skill.__table__.insert(),
        [
            {
                "id": required_id,
                "name": "Python",
                "slug": "gaps-required-python",
                "category": "TECHNOLOGY",
            },
            {
                "id": same_named_id,
                "name": "Python",
                "slug": "gaps-other-python",
                "category": "TECHNOLOGY",
            },
        ],
    )
    job_id = seed_job(
        isolated_database,
        title="Inference boundary",
        external_id="gaps-inference-boundary",
        posted_at=None,
    )
    isolated_database.execute(
        JobSkillRequirement.__table__.insert(),
        {
            "id": uuid4(),
            "job_id": job_id,
            "skill_id": required_id,
            "importance": "REQUIRED",
            "description": "Python required",
        },
    )
    resume_id, version_id, evidence_id = uuid4(), uuid4(), uuid4()
    isolated_database.execute(
        Resume.__table__.insert(), {"id": resume_id, "user_id": owner, "title": "Raw-text resume"}
    )
    isolated_database.execute(
        ResumeVersion.__table__.insert(),
        {
            "id": version_id,
            "resume_id": resume_id,
            "version_number": 1,
            "storage_key": "private/raw.pdf",
            "file_format": "PDF",
            "file_size_bytes": 1,
            "file_hash_sha256": "c" * 64,
            "parse_status": "PARSED_SUCCESS",
            "raw_extracted_text": "Python appears only in raw document text.",
        },
    )
    isolated_database.execute(
        ResumeEvidenceItem.__table__.insert(),
        {
            "id": evidence_id,
            "resume_version_id": version_id,
            "ordinal": 0,
            "category": "EXPERIENCE",
            "bullet_text": "Built Python services, but this item has no accepted skill link.",
        },
    )
    isolated_database.execute(
        UserSkill.__table__.insert(),
        {
            "id": uuid4(),
            "user_id": owner,
            "skill_id": same_named_id,
            "source": "USER",
            "confirmed_by_user": True,
        },
    )
    project_id = uuid4()
    isolated_database.execute(
        Project.__table__.insert(),
        {
            "id": project_id,
            "user_id": owner,
            "title": "Python title",
            "description": "Python appears only in this free-form project description.",
        },
    )
    isolated_database.execute(
        ProjectCustomSkill.__table__.insert(),
        {"id": uuid4(), "project_id": project_id, "value": "Python", "normalized_value": "python"},
    )
    isolated_database.execute(
        UserCustomSkill.__table__.insert(),
        {"id": uuid4(), "user_id": owner, "value": "Python", "normalized_value": "python"},
    )
    isolated_database.execute(
        UserPreferredSkill.__table__.insert(), {"user_id": owner, "skill_id": required_id}
    )
    isolated_database.execute(
        EmploymentRecord.__table__.insert(),
        {
            "id": uuid4(),
            "user_id": owner,
            "employer_name": "Python Co",
            "job_title": "Python Engineer",
            "start_date": date(2024, 1, 1),
            "end_date": date(2025, 1, 1),
            "description": "Python appears only in employment free text.",
        },
    )

    response = client.get(f"/api/v1/jobs/{job_id}/gaps", params={"resume_version_id": version_id})
    assert response.status_code == 200, response.text
    assert response.json()["covered"] == []
    assert response.json()["resume_presentation_gaps"] == []
    assert [item["requirement_id"] for item in response.json()["candidate_evidence_gaps"]] == [
        str(required_id)
    ]
