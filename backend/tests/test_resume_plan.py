"""Conservative, selected-version resume improvement plan reads."""

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


def test_resume_plan_maps_exact_gap_outcomes_and_preserves_provenance(isolated_database):
    client, owner = account()
    skills = catalog(isolated_database)
    job_id = seed_job(isolated_database, title="Plan job", external_id="plan-job", posted_at=None)
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
        f"/api/v1/jobs/{job_id}/resume-plan", params={"resume_version_id": selected_id}
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
        "job_title": "Plan job",
        "company_name": "Plan job Company",
        "resume_id": str(resume_id),
        "resume_title": "Targeted resume",
        "resume_version_id": str(selected_id),
        "resume_version_number": 1,
    }
    assert [item["name"] for item in body["keep"]] == ["Python"]
    assert [item["name"] for item in body["consider_adding_existing_evidence"]] == [
        "AWS",
        "Docker",
        "Terraform",
    ]
    assert [item["name"] for item in body["do_not_claim_without_evidence"]] == ["Kubernetes"]
    assert {item["requirement_id"] for item in body["manual_review"]} == {
        str(education_id),
        str(eligibility_id),
    }
    assert [item["action"] for item in body["keep"]] == ["KEEP"]
    assert all(
        item["action"] == "CONSIDER_ADDING_EXISTING_EVIDENCE"
        for item in body["consider_adding_existing_evidence"]
    )
    assert body["do_not_claim_without_evidence"][0]["action"] == "DO_NOT_CLAIM_WITHOUT_EVIDENCE"
    assert all(item["action"] == "MANUAL_REVIEW" for item in body["manual_review"])

    keep_source = body["keep"][0]["sources"]
    assert keep_source[0]["source_type"] == "RESUME_EVIDENCE"
    assert keep_source[0]["source_id"] == str(selected_item)
    assert keep_source[0]["resume_version_id"] == str(selected_id)
    actions = {item["name"]: item for item in body["consider_adding_existing_evidence"]}
    assert actions["Docker"]["sources"][0]["source_type"] == "CONFIRMED_BY_USER"
    assert actions["Docker"]["sources"][0]["source_id"] == str(confirmed_id)
    assert actions["AWS"]["sources"][0]["source_type"] == "PROJECT"
    assert actions["AWS"]["sources"][0]["source_id"] == str(project_id)
    assert actions["AWS"]["sources"][0]["project_title"] == "Catalog technology project"
    terraform_source = actions["Terraform"]["sources"]
    assert terraform_source[0]["source_type"] == "RESUME_EVIDENCE"
    assert terraform_source[0]["source_id"] == str(other_item)
    assert terraform_source[0]["resume_version_id"] == str(other_id)
    assert terraform_source[0]["resume_version_number"] == 2
    assert "Terraform" not in [item["name"] for item in body["keep"]]
    assert body["do_not_claim_without_evidence"][0]["sources"] == []
    assert body["do_not_claim_without_evidence"][0]["reason"] == (
        "No recorded supporting evidence supports adding Kubernetes to this resume."
    )
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


def test_resume_plan_is_owner_scoped_read_only_and_handles_missing_records_safely(
    isolated_database,
):
    client, owner = account()
    other, _ = account()
    skills = catalog(isolated_database)
    job_id = seed_job(
        isolated_database, title="Private plan", external_id="private-plan", posted_at=None
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
        f"/api/v1/jobs/{job_id}/resume-plan", params={"resume_version_id": selected_id}
    )
    second = client.get(
        f"/api/v1/jobs/{job_id}/resume-plan", params={"resume_version_id": selected_id}
    )
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert {table.name: list(isolated_database.execute(select(table)).mappings()) for table in tables} == before

    inaccessible = other.get(
        f"/api/v1/jobs/{job_id}/resume-plan", params={"resume_version_id": selected_id}
    )
    missing_version = client.get(
        f"/api/v1/jobs/{job_id}/resume-plan", params={"resume_version_id": uuid4()}
    )
    missing_job = client.get(
        f"/api/v1/jobs/{uuid4()}/resume-plan", params={"resume_version_id": selected_id}
    )
    unauthenticated = TestClient(app).get(
        f"/api/v1/jobs/{job_id}/resume-plan", params={"resume_version_id": selected_id}
    )
    write_attempt = client.post(
        f"/api/v1/jobs/{job_id}/resume-plan", params={"resume_version_id": selected_id}
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


def test_resume_plan_rejects_unsafe_or_ambiguous_query_inputs(isolated_database):
    client, owner = account()
    skills = catalog(isolated_database)
    job_id = seed_job(
        isolated_database, title="Query plan", external_id="query-plan", posted_at=None
    )
    job_requirements(isolated_database, job_id, skills)
    _, selected_id, _, _, _ = resume_versions(
        isolated_database, owner, skills["Python"], skills["Terraform"]
    )
    cases = (
        client.get(f"/api/v1/jobs/{job_id}/resume-plan"),
        client.get(
            f"/api/v1/jobs/{job_id}/resume-plan",
            params=[("resume_version_id", str(selected_id)), ("resume_version_id", str(uuid4()))],
        ),
        client.get(
            f"/api/v1/jobs/{job_id}/resume-plan",
            params={"resume_version_id": selected_id, "user_id": owner},
        ),
        client.get(f"/api/v1/jobs/{job_id}/gaps", params={"user_id": owner}),
    )
    assert [response.status_code for response in cases] == [422, 422, 422, 422]
    assert all(response.headers["cache-control"] == "no-store" for response in cases)


def test_resume_plan_never_infers_from_raw_text_preferences_or_free_text(isolated_database):
    client, owner = account()
    required_id, same_named_id = uuid4(), uuid4()
    isolated_database.execute(
        Skill.__table__.insert(),
        [
            {
                "id": required_id,
                "name": "Python",
                "slug": "plan-required-python",
                "category": "TECHNOLOGY",
            },
            {
                "id": same_named_id,
                "name": "Python",
                "slug": "plan-other-python",
                "category": "TECHNOLOGY",
            },
        ],
    )
    job_id = seed_job(
        isolated_database,
        title="Inference boundary",
        external_id="plan-inference-boundary",
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

    response = client.get(
        f"/api/v1/jobs/{job_id}/resume-plan", params={"resume_version_id": version_id}
    )
    assert response.status_code == 200, response.text
    assert response.json()["keep"] == []
    assert response.json()["consider_adding_existing_evidence"] == []
    assert [item["requirement_id"] for item in response.json()["do_not_claim_without_evidence"]] == [
        str(required_id)
    ]
