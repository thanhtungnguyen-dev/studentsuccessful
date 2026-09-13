"""Focused PostgreSQL coverage for Phase 20 canonical job resolution."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.ingestion.adapters import SourceAdapterRegistry
from backend.app.ingestion.dto import ExternalJobDTO
from backend.app.ingestion.live import (
    LiveJobSourceConfig,
    LiveSourceAdapter,
    LiveSourceFetchError,
)
from backend.app.main import app
from backend.app.models.application import Application
from backend.app.models.job import (
    JobLifecycle,
    JobSourceObservation,
    JobSourceRecord,
    NormalizedJob,
)
from backend.app.models.preference import CareerPreference
from backend.app.models.profile import ApplicationProfile, EducationRecord, EmploymentRecord
from backend.app.models.resume import Resume, ResumeEvidenceItem, ResumeVersion, UserSkill
from backend.app.models.taxonomy import Company, Role
from backend.app.models.user import User
from backend.app.repositories.job_ingestion import JobIngestionRepository
from backend.app.services import live_collection as live_collection_module
from backend.app.services.canonical_jobs import CanonicalJobService
from backend.app.services.job_ingestion import JobIngestionService, JobIngestionValidationError
from backend.app.services.live_collection import LiveCollectionService


@dataclass
class FixtureAdapter:
    key: str
    source_authority: str = "TRUSTED_STRUCTURED"

    def fetch(self):
        return ()


def registry(adapter_key: str, authority: str = "TRUSTED_STRUCTURED") -> SourceAdapterRegistry:
    return SourceAdapterRegistry([FixtureAdapter(adapter_key, authority)])


def seed_catalog(connection, *, company: str = "Acme"):
    company_id = uuid4()
    role_id = uuid4()
    connection.execute(Company.__table__.insert(), {"id": company_id, "name": company})
    connection.execute(
        Role.__table__.insert(),
        {
            "id": role_id,
            "name": "Software Engineer",
            "slug": f"software-engineer-{role_id}",
            "is_active": True,
        },
    )
    return company_id, role_id


def record(
    *,
    adapter_key: str = "fixture.alpha",
    external_id: str = "opening-1",
    source_url: str | None = None,
    application_url: str | None = None,
    title: str = "Software Engineer Intern",
    locations: tuple[str, ...] = ("Toronto, Canada",),
    description: str | None = "Structured source description.",
    source_status: str = "ACTIVE",
) -> ExternalJobDTO:
    base = adapter_key.replace(".", "-")
    return ExternalJobDTO(
        adapter_key=adapter_key,
        external_id=external_id,
        source_url=source_url or f"https://jobs-{base}.example.test/{external_id}",
        application_url=application_url
        or f"https://apply-{base}.example.test/{external_id}",
        company="Acme LLC",
        title=title,
        role="Software Engineer",
        employment_type="INTERNSHIP",
        career_level="UNSPECIFIED",
        work_mode="HYBRID",
        description=description,
        locations=locations,
        source_status=source_status,
    )


def ingest(item: ExternalJobDTO, authority: str = "TRUSTED_STRUCTURED"):
    with UnitOfWork() as uow:
        job = JobIngestionService.ingest(item, registry(item.adapter_key, authority), uow)
        return job.id


def reconcile_successful_source(adapter_key: str, observed_external_ids: tuple[str, ...]) -> None:
    with UnitOfWork() as uow:
        CanonicalJobService.record_successful_source_refresh(
            adapter_key,
            observed_external_ids,
            JobIngestionRepository(uow.session),
            uow.session,
            datetime.now(timezone.utc),
        )
        uow.commit()


def job_state(connection, job_id):
    return connection.execute(
        select(
            NormalizedJob.lifecycle,
            NormalizedJob.is_active,
            NormalizedJob.application_url,
            NormalizedJob.description,
            NormalizedJob.first_seen_at,
            NormalizedJob.last_seen_at,
            NormalizedJob.last_verified_at,
        ).where(NormalizedJob.id == job_id)
    ).one()


def test_repeated_source_identity_stays_one_observation_and_one_canonical_job(isolated_database):
    seed_catalog(isolated_database)
    item = record()
    first = ingest(item)
    second = ingest(item)

    assert first == second
    assert isolated_database.scalar(select(func.count()).select_from(JobSourceRecord)) == 1
    assert isolated_database.scalar(select(func.count()).select_from(JobSourceObservation)) == 1
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 1


def test_strong_cross_source_exact_company_title_location_merges_and_preserves_provenance(
    isolated_database,
):
    seed_catalog(isolated_database)
    first = ingest(record(adapter_key="fixture.alpha", external_id="alpha"))
    second = ingest(record(adapter_key="fixture.beta", external_id="beta"))

    assert first == second
    observations = isolated_database.execute(
        select(
            JobSourceObservation.canonical_job_id,
            JobSourceRecord.source_adapter,
            JobSourceRecord.external_id,
        )
        .join(
            JobSourceRecord,
            JobSourceRecord.id == JobSourceObservation.job_source_record_id,
        )
        .order_by(JobSourceRecord.source_adapter)
    ).all()
    assert [(row.source_adapter, row.external_id) for row in observations] == [
        ("fixture.alpha", "alpha"),
        ("fixture.beta", "beta"),
    ]
    assert {row.canonical_job_id for row in observations} == {first}


def test_same_company_title_with_different_locations_stays_separate(isolated_database):
    seed_catalog(isolated_database)
    toronto = ingest(record(external_id="toronto", locations=("Toronto, Canada",)))
    vancouver = ingest(
        record(
            adapter_key="fixture.beta",
            external_id="vancouver",
            locations=("Vancouver, Canada",),
        )
    )

    assert toronto != vancouver
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 2


def test_weak_title_similarity_without_exact_identity_stays_separate(isolated_database):
    seed_catalog(isolated_database)
    first = ingest(record(title="Software Engineer Intern"))
    second = ingest(
        record(
            adapter_key="fixture.beta",
            external_id="second",
            title="Software Engineering Internship",
        )
    )

    assert first != second


def test_matching_direct_official_application_url_is_strong_cross_source_identity(
    isolated_database,
):
    seed_catalog(isolated_database)
    apply_url = "https://apply.acme.example.test/opening-42"
    first = ingest(
        record(
            adapter_key="fixture.alpha",
            external_id="alpha",
            application_url=apply_url + "?utm_source=partner",
        )
    )
    second = ingest(
        record(
            adapter_key="fixture.beta",
            external_id="beta",
            application_url=apply_url,
            locations=("Vancouver, Canada",),
        )
    )

    assert first == second


def test_authoritative_facts_and_direct_official_apply_win_deterministically(isolated_database):
    seed_catalog(isolated_database)
    canonical = ingest(
        record(
            adapter_key="aggregator.alpha",
            external_id="agg",
            application_url="https://aggregator.example.test/opening",
            description="Aggregator summary.",
        ),
        authority="TRUSTED_AGGREGATOR",
    )
    same = ingest(
        record(
            adapter_key="official.beta",
            external_id="official",
            source_url="https://jobs.acme.example.test/opening",
            application_url="https://jobs.acme.example.test/opening/apply",
            description="Official complete description.",
        ),
        authority="OFFICIAL_ATS",
    )

    assert same == canonical
    state = job_state(isolated_database, canonical)
    assert state.description == "Official complete description."
    assert state.application_url == "https://jobs.acme.example.test/opening/apply"


def test_official_ats_page_beats_aggregator_fallback_when_no_direct_form(isolated_database):
    seed_catalog(isolated_database)
    canonical = ingest(
        record(
            adapter_key="aggregator.alpha",
            external_id="agg",
            application_url="https://aggregator.example.test/opening",
        ),
        authority="TRUSTED_AGGREGATOR",
    )
    ingest(
        record(
            adapter_key="official.beta",
            external_id="official",
            source_url="https://jobs.acme.example.test/opening",
            application_url="https://jobs.acme.example.test/opening",
        ),
        authority="OFFICIAL_ATS",
    )

    assert job_state(isolated_database, canonical).application_url == (
        "https://jobs.acme.example.test/opening"
    )


def test_unsafe_apply_url_rejects_before_canonical_source_state(isolated_database):
    seed_catalog(isolated_database)
    with pytest.raises(JobIngestionValidationError):
        ingest(record(application_url="javascript:alert(1)"))

    assert isolated_database.scalar(select(func.count()).select_from(JobSourceObservation)) == 0
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 0


def test_first_seen_is_preserved_and_reobservation_updates_verification(isolated_database):
    seed_catalog(isolated_database)
    canonical = ingest(record(description="First description."))
    before = job_state(isolated_database, canonical)
    ingest(record(description="Meaningfully updated description."))
    after = job_state(isolated_database, canonical)

    assert after.first_seen_at == before.first_seen_at
    assert after.last_seen_at >= before.last_seen_at
    assert after.last_verified_at >= before.last_verified_at
    assert after.description == "Meaningfully updated description."
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 1


def test_one_clean_successful_absence_marks_stale_but_not_closed(isolated_database):
    seed_catalog(isolated_database)
    canonical = ingest(record())
    reconcile_successful_source("fixture.alpha", ())

    state = job_state(isolated_database, canonical)
    assert (state.lifecycle, state.is_active) == (JobLifecycle.STALE, True)


def test_second_clean_successful_absence_closes_conservatively(isolated_database):
    seed_catalog(isolated_database)
    canonical = ingest(record())
    reconcile_successful_source("fixture.alpha", ())
    reconcile_successful_source("fixture.alpha", ())

    state = job_state(isolated_database, canonical)
    assert (state.lifecycle, state.is_active) == (JobLifecycle.CLOSED, False)


def test_other_current_source_keeps_canonical_job_open_when_one_source_disappears(
    isolated_database,
):
    seed_catalog(isolated_database)
    canonical = ingest(record(adapter_key="fixture.alpha", external_id="alpha"))
    ingest(record(adapter_key="fixture.beta", external_id="beta"))
    reconcile_successful_source("fixture.alpha", ())

    state = job_state(isolated_database, canonical)
    assert (state.lifecycle, state.is_active) == (JobLifecycle.ACTIVE, True)


def test_explicit_authoritative_closure_closes_canonical_job(isolated_database):
    seed_catalog(isolated_database)
    canonical = ingest(
        record(adapter_key="official.alpha", external_id="opening"),
        authority="OFFICIAL_ATS",
    )
    ingest(
        record(
            adapter_key="official.alpha",
            external_id="opening",
            source_status="CLOSED",
        ),
        authority="OFFICIAL_ATS",
    )

    assert job_state(isolated_database, canonical).lifecycle == JobLifecycle.CLOSED


@pytest.mark.parametrize("category", ["TIMEOUT", "RATE_LIMITED"])
def test_source_failure_or_rate_limit_does_not_close_existing_job(
    isolated_database,
    monkeypatch,
    category,
):
    seed_catalog(isolated_database)
    source_key = "greenhouse.phase20"
    canonical = ingest(
        record(adapter_key=source_key, external_id=category.lower()),
        authority="OFFICIAL_ATS",
    )
    config = LiveJobSourceConfig(
        key=source_key,
        family="greenhouse",
        board_token="phase20",
        company="Acme",
        role="Software Engineer",
        max_postings=10,
    )

    class FailingAdapter(LiveSourceAdapter):
        family = "greenhouse"

        def _records(self):
            raise LiveSourceFetchError("simulated failure", category=category)

        def _parse_record(self, raw):
            raise AssertionError("No source record should be parsed")

    monkeypatch.setattr(
        live_collection_module,
        "create_live_adapter",
        lambda configured, timeout_seconds: FailingAdapter(
            configured, timeout_seconds=timeout_seconds
        ),
    )
    service = LiveCollectionService(
        (config,),
        default_timeout_seconds=1,
        max_concurrency=1,
    )
    cycle = service.run_cycle(force=True)

    assert cycle.failed == 1
    assert job_state(isolated_database, canonical).lifecycle == JobLifecycle.ACTIVE


def test_closed_jobs_are_excluded_from_normal_jobs_listing(isolated_database):
    seed_catalog(isolated_database)
    canonical = ingest(
        record(adapter_key="official.alpha", external_id="opening"),
        authority="OFFICIAL_ATS",
    )
    ingest(
        record(
            adapter_key="official.alpha",
            external_id="opening",
            source_status="CLOSED",
        ),
        authority="OFFICIAL_ATS",
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"closed-{uuid4().hex}@example.com", "password": "Password123!"},
    )
    assert response.status_code == 201
    listing = client.get("/api/v1/jobs")
    assert listing.status_code == 200
    assert canonical not in {item["id"] for item in listing.json()["items"]}


def test_canonicalization_does_not_mutate_candidate_owned_data(isolated_database):
    seed_catalog(isolated_database)
    tables = (
        User.__table__,
        ApplicationProfile.__table__,
        UserSkill.__table__,
        CareerPreference.__table__,
        Resume.__table__,
        ResumeVersion.__table__,
        ResumeEvidenceItem.__table__,
        EducationRecord.__table__,
        EmploymentRecord.__table__,
        Application.__table__,
    )
    before = {
        table.name: isolated_database.scalar(select(func.count()).select_from(table))
        for table in tables
    }
    ingest(record(adapter_key="fixture.alpha", external_id="alpha"))
    ingest(record(adapter_key="fixture.beta", external_id="beta"))
    after = {
        table.name: isolated_database.scalar(select(func.count()).select_from(table))
        for table in tables
    }

    assert after == before


def test_concurrent_equivalent_ingestion_creates_one_canonical_job(database_engine):
    suffix = uuid4().hex[:16]
    company_name = f"Concurrent Acme {suffix}"
    role_slug = f"concurrent-role-{suffix}"
    adapter_keys = (f"fixture.concurrent{suffix}a", f"fixture.concurrent{suffix}b")
    factory = sessionmaker(bind=database_engine)
    with database_engine.begin() as connection:
        connection.execute(Company.__table__.insert(), {"id": uuid4(), "name": company_name})
        connection.execute(
            Role.__table__.insert(),
            {
                "id": uuid4(),
                "name": "Concurrent Engineer",
                "slug": role_slug,
                "is_active": True,
            },
        )

    def concurrent_record(adapter_key: str, external_id: str) -> ExternalJobDTO:
        return ExternalJobDTO(
            adapter_key=adapter_key,
            external_id=external_id,
            source_url=f"https://jobs-{external_id}.example.test/opening",
            application_url="https://apply.example.test/concurrent-opening",
            company=company_name,
            title="Concurrent Engineer",
            role="Concurrent Engineer",
            employment_type="INTERNSHIP",
            work_mode="HYBRID",
            locations=("Toronto, Canada",),
        )

    def work(item: ExternalJobDTO):
        with UnitOfWork(session_factory=factory) as uow:
            return JobIngestionService.ingest(item, registry(item.adapter_key), uow).id

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            job_ids = tuple(
                executor.map(
                    work,
                    (
                        concurrent_record(adapter_keys[0], "alpha"),
                        concurrent_record(adapter_keys[1], "beta"),
                    ),
                )
            )
        assert len(set(job_ids)) == 1
        with database_engine.connect() as connection:
            count = connection.scalar(
                select(func.count())
                .select_from(NormalizedJob)
                .join(
                    JobSourceRecord,
                    JobSourceRecord.id == NormalizedJob.job_source_record_id,
                )
                .where(JobSourceRecord.source_adapter.in_(adapter_keys))
            )
        assert count == 1
    finally:
        with database_engine.begin() as connection:
            connection.execute(
                delete(JobSourceRecord).where(JobSourceRecord.source_adapter.in_(adapter_keys))
            )
            connection.execute(delete(Company).where(Company.name == company_name))
            connection.execute(delete(Role).where(Role.slug == role_slug))
