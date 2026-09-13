"""Focused PostgreSQL and fixture coverage for Phase 18 public ATS ingestion."""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.commands.ingest_live import _selected_sources
from backend.app.ingestion.adapters import SourceAdapterRegistry
from backend.app.ingestion.live import (
    LiveJobSourceConfig,
    LiveSourceConfigurationError,
    LiveSourceFetchError,
    create_live_adapter,
    load_live_source_configs,
)
from backend.app.main import app
from backend.app.models.application import Application
from backend.app.models.job import JobSourceRecord, NormalizedJob, RawJobSnapshot
from backend.app.models.portfolio import Project
from backend.app.models.preference import CareerPreference
from backend.app.models.profile import (
    ApplicationProfile,
    EducationRecord,
    EmploymentRecord,
    WorkAuthorization,
)
from backend.app.models.resume import Resume, ResumeEvidenceItem, ResumeVersion, UserSkill
from backend.app.models.resume_review import ResumeTailoringReview
from backend.app.models.user import User
from backend.app.services.live_job_ingestion import LiveJobIngestionService


def source_config(family: str, *, key: str | None = None, **changes) -> LiveJobSourceConfig:
    values: dict[str, object] = {
        "key": key or f"{family}.acme",
        "family": family,
        "company": "Acme LLC",
        "role": "Unspecified",
        "enabled": True,
        "max_postings": 10,
    }
    values.update(
        {
            "greenhouse": {"board_token": "acme"},
            "lever": {"site": "acme"},
            "ashby": {"job_board": "Acme"},
        }[family]
    )
    values.update(changes)
    return LiveJobSourceConfig.model_validate(values)


def greenhouse_payload(*jobs: object) -> dict[str, object]:
    return {"jobs": list(jobs)}


def greenhouse_job(**changes) -> dict[str, object]:
    value: dict[str, object] = {
        "id": 101,
        "title": "Platform Engineering Intern",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/101",
        "content": "<p>Build <strong>platforms</strong>.</p>",
        "location": {"name": "Toronto, Canada"},
        "offices": [{"location": "Remote"}],
        "first_published": "2026-09-01T09:30:00Z",
        "updated_at": "2026-09-02T09:30:00Z",
    }
    value.update(changes)
    return value


def lever_job(**changes) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "lever-101",
        "text": "Software Engineering Intern",
        "hostedUrl": "https://jobs.lever.co/acme/lever-101",
        "applyUrl": "https://jobs.lever.co/acme/lever-101/apply",
        "descriptionPlain": "Build services.",
        "categories": {
            "location": "Toronto, Canada",
            "allLocations": ["Toronto, Canada", "Remote"],
            "commitment": "Intern",
        },
        "workplaceType": "hybrid",
    }
    value.update(changes)
    return value


def ashby_payload(*jobs: object) -> dict[str, object]:
    return {"apiVersion": "1", "jobs": list(jobs)}


def ashby_job(**changes) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "ashby-101",
        "title": "Product Intern",
        "jobUrl": "https://jobs.ashbyhq.com/acme/ashby-101",
        "applyUrl": "https://jobs.ashbyhq.com/acme/ashby-101/apply",
        "descriptionPlain": "Help ship a product.",
        "location": "Vancouver, Canada",
        "secondaryLocations": [{"location": "Remote"}],
        "isListed": True,
        "workplaceType": "Remote",
        "employmentType": "Intern",
        "publishedAt": "2026-09-03T12:00:00+00:00",
    }
    value.update(changes)
    return value


def response_client(payload: object, *, status: int = 200) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=payload))
    )


def adapter_for(config: LiveJobSourceConfig, payload: object) -> tuple[object, httpx.Client]:
    client = response_client(payload)
    return create_live_adapter(config, client=client), client


def ingest(config: LiveJobSourceConfig, payload: object):
    adapter, client = adapter_for(config, payload)
    try:
        return LiveJobIngestionService.ingest_adapter(adapter, SourceAdapterRegistry([adapter]))
    finally:
        client.close()


@pytest.mark.parametrize(
    ("family", "payload", "expected_id", "expected_apply", "expected_work_mode"),
    [
        (
            "greenhouse",
            greenhouse_payload(greenhouse_job()),
            "101",
            "https://boards.greenhouse.io/acme/jobs/101",
            "UNSPECIFIED",
        ),
        (
            "lever",
            [lever_job()],
            "lever-101",
            "https://jobs.lever.co/acme/lever-101/apply",
            "HYBRID",
        ),
        (
            "ashby",
            ashby_payload(ashby_job()),
            "ashby-101",
            "https://jobs.ashbyhq.com/acme/ashby-101/apply",
            "REMOTE",
        ),
    ],
)
def test_public_adapters_parse_representative_provider_records(
    family, payload, expected_id, expected_apply, expected_work_mode
):
    adapter, client = adapter_for(source_config(family), payload)
    try:
        records = adapter.fetch()
    finally:
        client.close()
    assert len(records) == 1
    record = records[0]
    assert record.external_id == expected_id
    assert record.adapter_key == f"{family}.acme"
    assert record.company == "Acme"
    assert record.application_url == expected_apply
    assert record.work_mode == expected_work_mode
    assert record.role == "Unspecified"


def test_adapter_keeps_known_source_timestamps_and_leaves_missing_optional_data_unknown():
    adapter, client = adapter_for(
        source_config("greenhouse"),
        greenhouse_payload(
            greenhouse_job(
                content=None,
                location=None,
                offices=None,
                first_published=None,
                updated_at=None,
            )
        ),
    )
    try:
        record = adapter.fetch()[0]
    finally:
        client.close()
    assert record.description is None
    assert record.locations == ()
    assert record.posted_at is None
    assert record.source_updated_at is None
    assert record.employment_type == "UNSPECIFIED"


def test_configuration_is_strict_and_supports_disabled_boards():
    configs = load_live_source_configs(
        json.dumps(
            [
                source_config("greenhouse").model_dump(),
                source_config("lever", enabled=False).model_dump(),
            ]
        )
    )
    assert [source.key for source in configs if source.enabled] == ["greenhouse.acme"]
    assert _selected_sources(configs, type("Args", (), {"source": None, "family": "lever"})()) == ()
    with pytest.raises(LiveSourceConfigurationError):
        load_live_source_configs('[{"key":"bad/key","family":"greenhouse"}]')


def test_malformed_provider_record_is_skipped_without_blocking_valid_record(isolated_database):
    result = ingest(
        source_config("greenhouse"),
        greenhouse_payload(
            greenhouse_job(),
            greenhouse_job(id=102, title=42),
        ),
    )
    assert (result.ingested, result.malformed, result.rejected) == (1, 1, 0)
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 1


def test_rate_limited_public_source_fails_before_any_database_write(isolated_database):
    client = response_client({"error": "slow down"}, status=429)
    adapter = create_live_adapter(source_config("greenhouse"), client=client)
    try:
        with pytest.raises(LiveSourceFetchError, match="HTTP 429"):
            adapter.fetch()
    finally:
        client.close()
    assert isolated_database.scalar(select(func.count()).select_from(JobSourceRecord)) == 0


def test_oversized_description_is_rejected_without_blocking_valid_posting(isolated_database):
    result = ingest(
        source_config("lever"),
        [lever_job(), lever_job(id="lever-large", descriptionPlain="x" * 20_001)],
    )
    assert (result.ingested, result.malformed, result.rejected) == (1, 0, 1)
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 1


def test_unsafe_application_url_is_rejected_without_corrupting_another_posting(isolated_database):
    result = ingest(
        source_config("lever"),
        [
            lever_job(),
            lever_job(id="lever-bad", applyUrl="javascript:alert(1)"),
        ],
    )
    assert (result.ingested, result.malformed, result.rejected) == (1, 0, 1)
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 1
    assert isolated_database.scalar(select(func.count()).select_from(JobSourceRecord)) == 1


def test_same_source_reingest_deduplicates_and_changed_posting_updates_existing_snapshot(
    isolated_database,
):
    config = source_config("ashby")
    first = ingest(config, ashby_payload(ashby_job()))
    repeated = ingest(config, ashby_payload(ashby_job()))
    changed = ingest(
        config,
        ashby_payload(ashby_job(descriptionPlain="Updated source description.", location="Toronto, Canada")),
    )
    assert first.ingested == repeated.ingested == changed.ingested == 1
    assert isolated_database.scalar(select(func.count()).select_from(JobSourceRecord)) == 1
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 1
    assert isolated_database.scalar(select(func.count()).select_from(RawJobSnapshot)) == 2
    assert isolated_database.scalar(select(NormalizedJob.description)) == "Updated source description."
    assert isolated_database.scalar(select(NormalizedJob.application_url)).endswith("/apply")


def test_source_provenance_and_official_application_destination_are_preserved(isolated_database):
    result = ingest(source_config("greenhouse"), greenhouse_payload(greenhouse_job()))
    assert result.ingested == 1
    source = isolated_database.execute(
        select(
            JobSourceRecord.source_adapter,
            JobSourceRecord.external_id,
            JobSourceRecord.source_url,
        )
    ).one()
    application_url = isolated_database.scalar(select(NormalizedJob.application_url))
    raw_payload = isolated_database.scalar(select(RawJobSnapshot.raw_payload))
    assert (source.source_adapter, source.external_id) == ("greenhouse.acme", "101")
    assert source.source_url == "https://boards.greenhouse.io/acme/jobs/101"
    assert application_url == source.source_url
    assert raw_payload["source_updated_at"] == "2026-09-02T09:30:00Z"


def test_live_ingestion_never_mutates_candidate_owned_records(isolated_database):
    tables = (
        User.__table__,
        UserSkill.__table__,
        CareerPreference.__table__,
        ApplicationProfile.__table__,
        Resume.__table__,
        ResumeVersion.__table__,
        ResumeEvidenceItem.__table__,
        Project.__table__,
        EducationRecord.__table__,
        EmploymentRecord.__table__,
        WorkAuthorization.__table__,
        ResumeTailoringReview.__table__,
        Application.__table__,
    )
    before = {
        table.name: isolated_database.scalar(select(func.count()).select_from(table)) for table in tables
    }
    result = ingest(source_config("ashby"), ashby_payload(ashby_job()))
    after = {
        table.name: isolated_database.scalar(select(func.count()).select_from(table)) for table in tables
    }
    assert result.ingested == 1
    assert after == before


def test_successful_live_ingestion_is_immediately_visible_through_jobs_api(isolated_database):
    ingest(source_config("greenhouse"), greenhouse_payload(greenhouse_job()))
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"live-jobs-{uuid4().hex}@example.com", "password": "Password123!"},
    )
    assert response.status_code == 201
    listing = client.get("/api/v1/jobs?keyword=Platform")
    assert listing.status_code == 200
    assert listing.headers["Cache-Control"] == "no-store"
    job = listing.json()["items"][0]
    assert job["title"] == "Platform Engineering Intern"
    assert job["source_name"] == "Greenhouse"
    assert "greenhouse.acme" not in json.dumps(job)
    detail = client.get(f"/api/v1/jobs/{job['id']}")
    assert detail.status_code == 200
    assert detail.json()["application_url"] == "https://boards.greenhouse.io/acme/jobs/101"
