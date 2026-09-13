"""Controlled, source-cited resume tailoring draft reads."""

import json
from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.main import app
from backend.app.models.job import JobSkillRequirement, NormalizedJob
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
from backend.tests.test_skill_gap import (
    account,
    add_project_technology,
    catalog,
    job_requirements,
    resume_versions,
)


def test_resume_draft_generates_only_conservative_supported_fragments_with_provenance(
    isolated_database,
):
    client, owner = account()
    skills = catalog(isolated_database)
    job_id = seed_job(isolated_database, title="Draft job", external_id="draft-job", posted_at=None)
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

    response = client.get(
        f"/api/v1/jobs/{job_id}/resume-draft", params={"resume_version_id": selected_id}
    )
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
        "job_title": "Draft job",
        "company_name": "Draft job Company",
        "resume_id": str(resume_id),
        "resume_title": "Targeted resume",
        "resume_version_id": str(selected_id),
        "resume_version_number": 1,
    }
    assert [item["name"] for item in body["keep"]] == ["Python"]
    assert body["keep"][0]["action"] == "KEEP"
    assert body["keep"][0]["draft_text"] is None
    assert body["keep"][0]["sources"][0]["source_id"] == str(selected_item)
    assert body["keep"][0]["sources"][0]["resume_version_id"] == str(selected_id)

    assert [item["name"] for item in body["draft_suggestions"]] == ["AWS", "Docker"]
    drafts = {item["name"]: item for item in body["draft_suggestions"]}
    assert drafts["AWS"]["draft_text"] == "Catalog technology project — AWS."
    assert drafts["AWS"]["sources"] == [
        {
            **drafts["AWS"]["sources"][0],
            "source_type": "PROJECT",
            "source_id": str(project_id),
            "project_id": str(project_id),
            "project_title": "Catalog technology project",
        }
    ]
    assert drafts["Docker"]["draft_text"] == "Docker."
    assert drafts["Docker"]["sources"][0]["source_type"] == "CONFIRMED_BY_USER"
    assert drafts["Docker"]["sources"][0]["source_id"] == str(confirmed_id)
    assert all(
        item["action"] == "CONSIDER_ADDING_EXISTING_EVIDENCE"
        for item in body["draft_suggestions"]
    )

    assert [item["name"] for item in body["unsupported"]] == ["Terraform", "Kubernetes"]
    assert all(item["draft_text"] is None for item in body["unsupported"])
    assert body["unsupported"][0]["action"] == "CONSIDER_ADDING_EXISTING_EVIDENCE"
    assert body["unsupported"][0]["sources"] == []
    assert "another resume version" in body["unsupported"][0]["limitation"].casefold()
    assert body["unsupported"][1]["action"] == "DO_NOT_CLAIM_WITHOUT_EVIDENCE"
    assert body["unsupported"][1]["sources"] == []
    assert {item["requirement_id"] for item in body["manual_review"]} == {
        str(education_id),
        str(eligibility_id),
    }
    assert all(item["action"] == "MANUAL_REVIEW" for item in body["manual_review"])
    assert all(item["draft_text"] is None for item in body["manual_review"])

    serialized = json.dumps(body)
    for forbidden in (
        str(other_id),
        str(other_item),
        "Unlinked raw text",
        "storage_key",
        "file_hash_sha256",
        "raw_extracted_text",
        "private/selected.pdf",
        "private ingestion source",
    ):
        assert forbidden not in serialized


def test_resume_draft_is_owner_scoped_read_only_and_handles_missing_records_safely(
    isolated_database,
):
    client, owner = account()
    other, _ = account()
    skills = catalog(isolated_database)
    job_id = seed_job(
        isolated_database, title="Private draft", external_id="private-draft", posted_at=None
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
    first = client.get(
        f"/api/v1/jobs/{job_id}/resume-draft", params={"resume_version_id": selected_id}
    )
    second = client.get(
        f"/api/v1/jobs/{job_id}/resume-draft", params={"resume_version_id": selected_id}
    )
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert {table.name: list(isolated_database.execute(select(table)).mappings()) for table in tables} == before

    inaccessible = other.get(
        f"/api/v1/jobs/{job_id}/resume-draft", params={"resume_version_id": selected_id}
    )
    missing_version = client.get(
        f"/api/v1/jobs/{job_id}/resume-draft", params={"resume_version_id": uuid4()}
    )
    missing_job = client.get(
        f"/api/v1/jobs/{uuid4()}/resume-draft", params={"resume_version_id": selected_id}
    )
    unauthenticated = TestClient(app).get(
        f"/api/v1/jobs/{job_id}/resume-draft", params={"resume_version_id": selected_id}
    )
    write_attempt = client.post(
        f"/api/v1/jobs/{job_id}/resume-draft", params={"resume_version_id": selected_id}
    )
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


def test_resume_draft_rejects_unsafe_or_ambiguous_query_inputs(isolated_database):
    client, owner = account()
    skills = catalog(isolated_database)
    job_id = seed_job(
        isolated_database, title="Query draft", external_id="query-draft", posted_at=None
    )
    job_requirements(isolated_database, job_id, skills)
    _, selected_id, _, _, _ = resume_versions(
        isolated_database, owner, skills["Python"], skills["Terraform"]
    )
    cases = (
        client.get(f"/api/v1/jobs/{job_id}/resume-draft"),
        client.get(
            f"/api/v1/jobs/{job_id}/resume-draft",
            params=[("resume_version_id", str(selected_id)), ("resume_version_id", str(uuid4()))],
        ),
        client.get(
            f"/api/v1/jobs/{job_id}/resume-draft",
            params={"resume_version_id": selected_id, "user_id": owner},
        ),
        client.get(f"/api/v1/jobs/{job_id}/resume-plan", params={"draft": "true"}),
    )
    assert [response.status_code for response in cases] == [422, 422, 422, 422]
    assert all(response.headers["cache-control"] == "no-store" for response in cases)


def test_resume_draft_never_infers_from_raw_text_preferences_or_free_text(isolated_database):
    client, owner = account()
    required_id, same_named_id = uuid4(), uuid4()
    isolated_database.execute(
        Skill.__table__.insert(),
        [
            {
                "id": required_id,
                "name": "Python",
                "slug": "draft-required-python",
                "category": "TECHNOLOGY",
            },
            {
                "id": same_named_id,
                "name": "Python",
                "slug": "draft-other-python",
                "category": "TECHNOLOGY",
            },
        ],
    )
    job_id = seed_job(
        isolated_database,
        title="Inference boundary",
        external_id="draft-inference-boundary",
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
            "raw_extracted_text": "Improved query performance by 40% with Python.",
        },
    )
    isolated_database.execute(
        ResumeEvidenceItem.__table__.insert(),
        {
            "id": evidence_id,
            "resume_version_id": version_id,
            "ordinal": 0,
            "category": "EXPERIENCE",
            "bullet_text": "Built Python services and improved performance by 40%, but no skill link exists.",
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

    response = client.get(
        f"/api/v1/jobs/{job_id}/resume-draft", params={"resume_version_id": version_id}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["keep"] == []
    assert body["draft_suggestions"] == []
    assert [item["requirement_id"] for item in body["unsupported"]] == [str(required_id)]
    assert body["unsupported"][0]["action"] == "DO_NOT_CLAIM_WITHOUT_EVIDENCE"
    assert body["unsupported"][0]["draft_text"] is None
    serialized = json.dumps(body)
    for forbidden in ("40%", "Improved", "Built Python", "Python title", "Python Co"):
        assert forbidden not in serialized
