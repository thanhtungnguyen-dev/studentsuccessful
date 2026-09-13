"""Security regressions for authenticated, shared Phase 9 job browsing."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.main import app
from backend.app.models.job import (
    JobEducationRequirement,
    JobEligibilityRequirement,
    JobLocation,
    JobSkillRequirement,
    JobSourceRecord,
    NormalizedJob,
    RawJobSnapshot,
)
from backend.app.models.resume import Resume, ResumeVersion, UserSkill
from backend.app.models.taxonomy import Company, Role, Skill

URL = "/api/v1/jobs"
RAW_SENTINEL = "<script>window.privateJobPayload = true</script>"
CANDIDATE_SENTINEL = "candidate-secret-skill"
PROVENANCE_SENTINEL = "private-ingestion-provenance"


def account() -> tuple[TestClient, UUID, str]:
    client = TestClient(app)
    email = f"job-security-{uuid4().hex}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!"},
    )
    assert response.status_code == 201
    return client, UUID(response.json()["user"]["id"]), email


def seed_job(
    connection,
    *,
    active: bool = True,
    description: str = "Normalized job description",
    with_untrusted_location: bool = False,
) -> UUID:
    company_id, role_id, source_id, job_id = (uuid4() for _ in range(4))
    connection.execute(
        Company.__table__.insert(),
        {"id": company_id, "name": "Shared employer", "is_verified": True},
    )
    connection.execute(
        Role.__table__.insert(),
        {"id": role_id, "name": "Shared role", "slug": f"shared-role-{role_id}", "is_active": True},
    )
    connection.execute(
        JobSourceRecord.__table__.insert(),
        {
            "id": source_id,
            "source_adapter": "PRIVATE_INGESTION_SENTINEL",
            "external_id": "private-external-id",
            "source_url": "https://private-source.example/credential",
        },
    )
    connection.execute(
        RawJobSnapshot.__table__.insert(),
        {
            "id": uuid4(),
            "job_source_record_id": source_id,
            "raw_payload": {"description": RAW_SENTINEL, "private_token": "do-not-return"},
            "payload_hash_sha256": "a" * 64,
        },
    )
    connection.execute(
        NormalizedJob.__table__.insert(),
        {
            "id": job_id,
            "job_source_record_id": source_id,
            "company_id": company_id,
            "title": "Shared internship",
            "description": description,
            "role_id": role_id,
            "employment_type": "INTERNSHIP",
            "career_level": "STUDENT",
            "work_mode": "REMOTE",
            "application_url": "https://apply.example/shared",
            "is_active": active,
            "posted_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        },
    )
    if with_untrusted_location:
        connection.execute(
            JobLocation.__table__.insert(),
            {"id": uuid4(), "job_id": job_id, "location_raw": RAW_SENTINEL},
        )
    return job_id


def seed_candidate_private_data(connection, user_id: UUID) -> None:
    skill_id, resume_id, version_id = uuid4(), uuid4(), uuid4()
    connection.execute(
        Skill.__table__.insert(),
        {
            "id": skill_id,
            "name": CANDIDATE_SENTINEL,
            "slug": CANDIDATE_SENTINEL,
            "category": "TECHNOLOGY",
        },
    )
    connection.execute(
        UserSkill.__table__.insert(),
        {
            "id": uuid4(),
            "user_id": user_id,
            "skill_id": skill_id,
            "source": "USER",
            "confirmed_by_user": True,
            "user_notes": CANDIDATE_SENTINEL,
        },
    )
    connection.execute(
        Resume.__table__.insert(),
        {"id": resume_id, "user_id": user_id, "title": "Private candidate resume"},
    )
    connection.execute(
        ResumeVersion.__table__.insert(),
        {
            "id": version_id,
            "resume_id": resume_id,
            "version_number": 1,
            "storage_key": "private/candidate.pdf",
            "file_format": "PDF",
            "file_size_bytes": 1,
            "file_hash_sha256": "b" * 64,
            "parse_status": "PARSED_SUCCESS",
            "raw_extracted_text": CANDIDATE_SENTINEL,
        },
    )


def seed_requirements(connection, job_id: UUID) -> UUID:
    skill_id = uuid4()
    connection.execute(
        Skill.__table__.insert(),
        {
            "id": skill_id,
            "name": "Public requirement skill",
            "slug": f"public-{skill_id}",
            "category": "TECHNOLOGY",
        },
    )
    connection.execute(
        JobSkillRequirement.__table__.insert(),
        {
            "id": uuid4(),
            "job_id": job_id,
            "skill_id": skill_id,
            "importance": "REQUIRED",
            "description": "Required experience",
        },
    )
    connection.execute(
        JobEducationRequirement.__table__.insert(),
        {
            "id": uuid4(),
            "job_id": job_id,
            "degree_level": "BS",
            "target_grad_start": date(2026, 5, 1),
            "target_grad_end": date(2027, 5, 1),
        },
    )
    connection.execute(
        JobEligibilityRequirement.__table__.insert(),
        {
            "id": uuid4(),
            "job_id": job_id,
            "requirement_type": "WORK_AUTHORIZATION",
            "value": "AUTHORIZED",
            "description": "May work in Canada",
            "source_evidence": PROVENANCE_SENTINEL,
        },
    )
    return skill_id


def test_job_reads_require_a_session_and_reject_user_scope_injection(isolated_database):
    job_id = seed_job(isolated_database)
    anonymous = TestClient(app)
    for path in (URL, f"{URL}/{job_id}"):
        response = anonymous.get(path)
        assert response.status_code == 401
        assert response.json()["code"] == "UNAUTHENTICATED"

    client, _, _ = account()
    for path in (f"{URL}?user_id={uuid4()}", f"{URL}/{job_id}?user_id={uuid4()}"):
        response = client.get(path)
        assert response.status_code == 422


def test_inactive_and_missing_jobs_are_indistinguishable_to_authenticated_viewers(
    isolated_database,
):
    inactive = seed_job(isolated_database, active=False)
    client, _, _ = account()
    hidden = client.get(f"{URL}/{inactive}")
    missing = client.get(f"{URL}/{uuid4()}")

    assert hidden.status_code == missing.status_code == 404
    assert hidden.json() == missing.json() | {"instance": f"{URL}/{inactive}"}
    assert hidden.json()["code"] == "JOB_NOT_FOUND"


def test_authenticated_job_reads_do_not_expose_ingestion_or_candidate_data(isolated_database):
    job_id = seed_job(isolated_database)
    client, user_id, email = account()
    seed_candidate_private_data(isolated_database, user_id)

    responses = (client.get(URL), client.get(f"{URL}/{job_id}"))
    forbidden = (
        RAW_SENTINEL,
        CANDIDATE_SENTINEL,
        email,
        str(user_id),
        "PRIVATE_INGESTION_SENTINEL",
        "private-external-id",
        "private-source.example",
        "raw_payload",
        "payload_hash_sha256",
        "job_source_record_id",
        "storage_key",
        "raw_extracted_text",
        "user_notes",
    )
    for response in responses:
        assert response.status_code == 200, response.text
        payload = json.dumps(response.json())
        assert not any(value in payload for value in forbidden)


def test_job_detail_allows_only_safe_requirement_fields_and_excludes_provenance(isolated_database):
    job_id = seed_job(isolated_database)
    skill_id = seed_requirements(isolated_database, job_id)
    client, _, _ = account()

    response = client.get(f"{URL}/{job_id}")
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["skill_requirements"] == [{
        "skill_id": str(skill_id),
        "skill_name": "Public requirement skill",
        "skill_category": "TECHNOLOGY",
        "importance": "REQUIRED",
        "description": "Required experience",
    }]
    assert set(detail["education_requirements"][0]) == {
        "id", "degree_level", "target_grad_start", "target_grad_end"
    }
    assert detail["education_requirements"][0]["degree_level"] == "BS"
    assert detail["education_requirements"][0]["target_grad_start"] == "2026-05-01"
    assert detail["education_requirements"][0]["target_grad_end"] == "2027-05-01"
    assert set(detail["eligibility_requirements"][0]) == {
        "id", "requirement_type", "value", "description"
    }
    assert detail["eligibility_requirements"][0]["description"] == "May work in Canada"
    serialized = json.dumps(detail)
    assert PROVENANCE_SENTINEL not in serialized
    assert "source_evidence" not in serialized


def test_untrusted_listing_text_stays_json_data_and_job_gets_are_read_only(isolated_database):
    job_id = seed_job(
        isolated_database,
        description=RAW_SENTINEL,
        with_untrusted_location=True,
    )
    client, _, _ = account()
    statements: list[str] = []

    def capture(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(isolated_database, "before_cursor_execute", capture)
    try:
        with patch.object(
            UnitOfWork,
            "commit",
            autospec=True,
            side_effect=AssertionError("job GET must not commit"),
        ) as commit:
            detail = client.get(f"{URL}/{job_id}")
            listing = client.get(URL)
        commit.assert_not_called()
    finally:
        event.remove(isolated_database, "before_cursor_execute", capture)

    assert detail.status_code == listing.status_code == 200
    assert detail.headers["content-type"].startswith("application/json")
    assert detail.json()["description"] == RAW_SENTINEL
    assert detail.json()["locations"] == [RAW_SENTINEL]
    assert not any(
        statement.lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE "))
        for statement in statements
    )
