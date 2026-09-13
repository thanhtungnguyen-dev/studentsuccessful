"""PostgreSQL coverage for the private Phase 10 job-ingestion boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.ingestion.adapters import SourceAdapterRegistry
from backend.app.ingestion.dto import (
    ExternalJobDTO,
    ExternalJobEducationRequirement,
    ExternalJobEligibilityRequirement,
    ExternalJobSkillRequirement,
)
from backend.app.main import app
from backend.app.models.application import Application
from backend.app.models.job import (
    JobEducationRequirement,
    JobEligibilityRequirement,
    JobLocation,
    JobSkillRequirement,
    JobSourceRecord,
    NormalizedJob,
    RawJobSnapshot,
)
from backend.app.models.resume import UserSkill
from backend.app.models.taxonomy import Company, Industry, Role, Skill, SkillAlias
from backend.app.models.user import User
from backend.app.services import job_ingestion as job_ingestion_module
from backend.app.services.job_ingestion import JobIngestionService, JobIngestionValidationError


@dataclass
class FixtureAdapter:
    key: str = "fixture.ats"
    rows: tuple[ExternalJobDTO, ...] = field(default_factory=tuple)

    def fetch(self):
        return self.rows


def registry(*rows: ExternalJobDTO) -> SourceAdapterRegistry:
    return SourceAdapterRegistry([FixtureAdapter(rows=rows)])


def seed_catalog(connection):
    company_id, role_id, skill_id, industry_id = (uuid4() for _ in range(4))
    connection.execute(Company.__table__.insert(), {"id": company_id, "name": "Google"})
    connection.execute(
        Role.__table__.insert(),
        {"id": role_id, "name": "Software Engineer", "slug": "software-engineer", "is_active": True},
    )
    connection.execute(
        Skill.__table__.insert(),
        {"id": skill_id, "name": "Python", "slug": "python", "category": "TECHNOLOGY", "is_active": True},
    )
    connection.execute(
        SkillAlias.__table__.insert(),
        {"id": uuid4(), "skill_id": skill_id, "alias": "Py", "normalized_alias": "py"},
    )
    connection.execute(
        Industry.__table__.insert(), {"id": industry_id, "name": "Technology", "slug": "technology"}
    )
    return company_id, role_id, skill_id, industry_id


def record(**changes) -> ExternalJobDTO:
    values = {
        "adapter_key": "fixture.ats",
        "external_id": "google-swe-123",
        "source_url": "https://jobs.example/google-swe-123",
        "application_url": "https://apply.example/google-swe-123",
        "company": " Google LLC ",
        "title": "  Software   Engineer Intern ",
        "role": "Software Engineer",
        "employment_type": "INTERNSHIP",
        "career_level": "STUDENT",
        "work_mode": "REMOTE",
        "description": " Build\nuseful systems. ",
        "posted_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
        "locations": (" remote ", "Toronto Canada"),
        "skills": (ExternalJobSkillRequirement(skill="py", importance="REQUIRED"),),
        "education_requirements": (
            ExternalJobEducationRequirement(
                degree_level="BS", target_grad_start=date(2026, 5, 1), target_grad_end=date(2027, 5, 1)
            ),
        ),
        "eligibility_requirements": (
            ExternalJobEligibilityRequirement(
                requirement_type="WORK_AUTHORIZATION", value="CA", description="May work in Canada"
            ),
        ),
        "industries": ("Technology",),
    }
    values.update(changes)
    return ExternalJobDTO(**values)


def account() -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"ingestion-{uuid4().hex}@example.com", "password": "Password123!"},
    )
    assert response.status_code == 201
    return client


def test_first_ingest_normalizes_catalog_facts_and_is_visible_as_a_shared_job(isolated_database):
    _, _, python_id, _ = seed_catalog(isolated_database)
    source = record(external_id="PHASE10_PRIVATE_EXTERNAL_ID")
    with UnitOfWork() as uow:
        JobIngestionService.ingest(source, registry(), uow)

    with UnitOfWork() as uow:
        job = uow.session.scalar(select(NormalizedJob))
        snapshot = uow.session.scalar(select(RawJobSnapshot))
        assert job.title == "Software Engineer Intern"
        assert job.description == "Build useful systems."
        assert uow.session.scalars(select(JobLocation.location_raw).order_by(JobLocation.location_raw)).all() == [
            "Remote",
            "Toronto, Canada",
        ]
        assert uow.session.scalar(select(JobSkillRequirement.skill_id)) == python_id
        assert snapshot.payload_hash_sha256 == snapshot.payload_hash_sha256.lower()
        assert snapshot.raw_payload["company"] == "Google"
        assert snapshot.raw_payload["locations"] == ["Remote", "Toronto, Canada"]
        assert "raw_payload" not in snapshot.raw_payload
        assert "source_evidence" not in snapshot.raw_payload["eligibility_requirements"][0]
        job_id = job.id

    client = account()
    detail = client.get(f"/api/v1/jobs/{job_id}")
    assert detail.status_code == 200
    assert detail.json()["company_name"] == "Google"
    assert detail.json()["locations"] == ["Remote", "Toronto, Canada"]
    public_payload = json.dumps(detail.json())
    assert source.source_url not in public_payload
    assert source.external_id not in public_payload
    assert source.adapter_key not in public_payload
    assert "raw_payload" not in public_payload
    assert "payload_hash_sha256" not in public_payload


def test_duplicate_reingest_is_idempotent_and_changed_payload_replaces_complete_fact_sets(
    isolated_database,
    monkeypatch,
):
    seed_catalog(isolated_database)
    first = record()
    first_verified = datetime(2026, 4, 2, 10, tzinfo=timezone.utc)
    second_verified = datetime(2026, 4, 3, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(
        job_ingestion_module,
        "datetime",
        type("Clock", (), {"now": staticmethod(lambda _timezone: first_verified)}),
    )
    with UnitOfWork() as uow:
        first_job = JobIngestionService.ingest(first, registry(), uow)
        first_job_id = first_job.id
        first_payload_hash = first_job.current_payload_hash_sha256
        assert first_job.last_verified_at == first_verified
    monkeypatch.setattr(
        job_ingestion_module,
        "datetime",
        type("Clock", (), {"now": staticmethod(lambda _timezone: second_verified)}),
    )
    with UnitOfWork() as uow:
        repeat_job = JobIngestionService.ingest(first, registry(), uow)
        repeat_job_id = repeat_job.id
        assert repeat_job.last_verified_at == second_verified
    assert first_job_id == repeat_job_id

    with UnitOfWork() as uow:
        assert uow.session.scalar(select(func.count()).select_from(RawJobSnapshot)) == 1
        assert uow.session.scalar(select(NormalizedJob.last_verified_at)) == second_verified

    changed = record(
        source_url="https://jobs.example/google-swe-123?edition=2",
        description="Changed source facts",
        locations=("Remote",),
        skills=(),
        education_requirements=(),
        eligibility_requirements=(),
        industries=(),
    )
    with UnitOfWork() as uow:
        changed_job = JobIngestionService.ingest(changed, registry(), uow)
        changed_job_id = changed_job.id
    assert changed_job_id == first_job_id

    with UnitOfWork() as uow:
        assert uow.session.scalar(select(func.count()).select_from(JobSourceRecord)) == 1
        assert uow.session.scalar(select(func.count()).select_from(RawJobSnapshot)) == 2
        assert uow.session.scalar(select(JobSourceRecord.source_url)) == first.source_url
        assert uow.session.scalar(select(NormalizedJob.description)) == "Changed source facts"
        assert uow.session.scalar(select(func.count()).select_from(JobLocation)) == 1
        assert uow.session.scalar(select(func.count()).select_from(JobSkillRequirement)) == 0
        assert uow.session.scalar(select(func.count()).select_from(JobEducationRequirement)) == 0
        assert uow.session.scalar(select(func.count()).select_from(JobEligibilityRequirement)) == 0

    # A historical snapshot can recur after a changed source payload. It must
    # restore the normalized job without storing a third copy of that snapshot.
    with UnitOfWork() as uow:
        restored_job = JobIngestionService.ingest(first, registry(), uow)
        assert restored_job.id == first_job_id
    with UnitOfWork() as uow:
        assert uow.session.scalar(select(func.count()).select_from(RawJobSnapshot)) == 2
        assert uow.session.scalar(select(NormalizedJob.description)) == "Build useful systems."
        assert uow.session.scalar(select(NormalizedJob.current_payload_hash_sha256)) == first_payload_hash
        assert uow.session.scalar(select(func.count()).select_from(JobLocation)) == 2
        assert uow.session.scalar(select(func.count()).select_from(JobSkillRequirement)) == 1


@pytest.mark.parametrize(
    "bad",
    [
        record(application_url="https://user:password@apply.example/job"),
        record(source_url="https://jobs.example:bad/job"),
        record(posted_at=datetime(2026, 4, 1)),
        record(
            education_requirements=(
                ExternalJobEducationRequirement(
                    degree_level="BS",
                    target_grad_start=date(2028, 5, 1),
                    target_grad_end=date(2027, 5, 1),
                ),
            )
        ),
        record(adapter_key="unsupported"),
        record(skills=(ExternalJobSkillRequirement(skill="py"), ExternalJobSkillRequirement(skill="Python"))),
    ],
)
def test_invalid_records_rollback_without_source_snapshot_or_job_rows(isolated_database, bad):
    seed_catalog(isolated_database)
    with UnitOfWork() as uow:
        with pytest.raises(JobIngestionValidationError):
            JobIngestionService.ingest(bad, registry(), uow)
    with UnitOfWork() as uow:
        assert uow.session.scalar(select(func.count()).select_from(JobSourceRecord)) == 0
        assert uow.session.scalar(select(func.count()).select_from(RawJobSnapshot)) == 0
        assert uow.session.scalar(select(func.count()).select_from(NormalizedJob)) == 0


def test_adapter_rejects_non_dto_results_before_any_database_write(isolated_database):
    seed_catalog(isolated_database)
    bad_registry = SourceAdapterRegistry([FixtureAdapter(rows=("not-a-job-dto",))])
    with UnitOfWork() as uow:
        with pytest.raises(JobIngestionValidationError, match="ExternalJobDTO"):
            JobIngestionService.ingest_from_adapter("fixture.ats", bad_registry, uow)
    assert isolated_database.scalar(select(func.count()).select_from(JobSourceRecord)) == 0


@pytest.mark.parametrize("ambiguous", ["company", "role", "industry", "skill_name", "skill_alias"])
def test_ambiguous_catalog_references_are_rejected_without_writes(isolated_database, ambiguous):
    _, _, python_id, _ = seed_catalog(isolated_database)
    if ambiguous == "company":
        isolated_database.execute(Company.__table__.insert(), {"id": uuid4(), "name": "Google"})
        bad = record()
    elif ambiguous == "role":
        isolated_database.execute(
            Role.__table__.insert(),
            {
                "id": uuid4(),
                "name": "Software Engineer",
                "slug": "duplicate-software-engineer",
                "is_active": True,
            },
        )
        bad = record()
    elif ambiguous == "industry":
        isolated_database.execute(
            Industry.__table__.insert(),
            {"id": uuid4(), "name": "Technology", "slug": "duplicate-technology"},
        )
        bad = record()
    else:
        other_skill_id = uuid4()
        isolated_database.execute(
            Skill.__table__.insert(),
            {
                "id": other_skill_id,
                "name": "Python" if ambiguous == "skill_name" else "Machine Learning",
                "slug": f"duplicate-{ambiguous}",
                "category": "TECHNOLOGY",
                "is_active": True,
            },
        )
        if ambiguous == "skill_alias":
            isolated_database.execute(
                SkillAlias.__table__.insert(),
                [
                    {"id": uuid4(), "skill_id": python_id, "alias": "ML", "normalized_alias": "ml"},
                    {"id": uuid4(), "skill_id": other_skill_id, "alias": "ML", "normalized_alias": "ml"},
                ],
            )
            bad = record(skills=(ExternalJobSkillRequirement(skill="ML"),))
        else:
            bad = record(skills=(ExternalJobSkillRequirement(skill="Python"),))

    with UnitOfWork() as uow:
        with pytest.raises(JobIngestionValidationError):
            JobIngestionService.ingest(bad, registry(), uow)
    assert isolated_database.scalar(select(func.count()).select_from(JobSourceRecord)) == 0
    assert isolated_database.scalar(select(func.count()).select_from(RawJobSnapshot)) == 0
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 0


def test_ingestion_never_writes_candidates_or_applications_and_has_no_public_mutation_route(
    isolated_database,
):
    seed_catalog(isolated_database)
    before_users = isolated_database.scalar(select(func.count()).select_from(User))
    before_user_skills = isolated_database.scalar(select(func.count()).select_from(UserSkill))
    before_applications = isolated_database.scalar(select(func.count()).select_from(Application))
    with UnitOfWork() as uow:
        JobIngestionService.ingest_from_adapter("fixture.ats", registry(record()), uow)

    assert isolated_database.scalar(select(func.count()).select_from(User)) == before_users
    assert isolated_database.scalar(select(func.count()).select_from(UserSkill)) == before_user_skills
    assert isolated_database.scalar(select(func.count()).select_from(Application)) == before_applications
    assert TestClient(app).post("/api/v1/jobs").status_code == 405
