"""Focused offline coverage for Phase 21 reusable public source families."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import backend.app.services.live_collection as collection_module
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
from backend.app.models.job import (
    JobSourceObservation,
    JobSourceRecord,
    LiveSourceHealth,
    LiveSourceState,
    NormalizedJob,
)
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
from backend.app.services.live_collection import LiveCollectionService
from backend.app.services.live_job_ingestion import LiveJobIngestionService

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def source_config(family: str, *, key: str | None = None, **changes) -> LiveJobSourceConfig:
    values: dict[str, object] = {
        "key": key or f"{family}.acme",
        "family": family,
        "company": "Acme LLC",
        "role": "Unspecified",
        "enabled": True,
        "max_postings": 10,
        "poll_interval_seconds": 300,
    }
    values.update(
        {
            "smartrecruiters": {"company_identifier": "acme"},
            "rss": {
                "feed_url": "https://careers.acme.example/jobs.xml",
                "allowed_job_hosts": ["jobs.acme.example", "apply.acme.example"],
            },
        }[family]
    )
    values.update(changes)
    return LiveJobSourceConfig.model_validate(values)


def smart_listing_job(identifier: str = "sr-101", **changes) -> dict[str, object]:
    value: dict[str, object] = {
        "id": identifier,
        "name": "Platform Engineering Intern",
        "location": {
            "city": "Denver",
            "region": "CO",
            "country": "US",
            "remote": True,
        },
        "typeOfEmployment": {"label": "Internship"},
    }
    value.update(changes)
    return value


def smart_detail(identifier: str = "sr-101", **changes) -> dict[str, object]:
    value: dict[str, object] = {
        **smart_listing_job(identifier),
        "postingUrl": f"https://jobs.smartrecruiters.com/acme/{identifier}",
        "applyUrl": f"https://apply.smartrecruiters.com/acme/{identifier}",
        "releasedDate": "2026-09-01T09:30:00Z",
        "updatedAt": "2026-09-02T09:30:00Z",
        "active": True,
        "jobAd": {
            "sections": {
                "jobDescription": {"text": "<p>Build <strong>platforms</strong>.</p>"},
                "qualifications": {"text": "<p>Learn quickly.</p>"},
            }
        },
    }
    value.update(changes)
    return value


def rss_document(*items: str) -> bytes:
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<rss version='2.0'><channel><title>Acme Careers</title>"
        + "".join(items)
        + "</channel></rss>"
    ).encode()


def rss_item(
    identifier: str = "feed-101",
    *,
    title: str = "Software Engineering Co-op",
    link: str = "https://jobs.acme.example/feed-101",
    apply_url: str | None = "https://apply.acme.example/feed-101",
    description: str | None = "<p>Build reliable services.</p>",
    employment_type: str | None = "Co-op",
    location: str | None = "Toronto, Canada",
    published: str | None = "Tue, 01 Sep 2026 09:30:00 +0000",
) -> str:
    fields = [
        f"<guid>{identifier}</guid>",
        f"<title>{title}</title>",
        f"<link>{link}</link>",
    ]
    if apply_url is not None:
        fields.append(f"<applicationUrl>{apply_url}</applicationUrl>")
    if description is not None:
        fields.append(f"<description><![CDATA[{description}]]></description>")
    if employment_type is not None:
        fields.append(f"<employmentType>{employment_type}</employmentType>")
    if location is not None:
        fields.append(f"<location>{location}</location>")
    if published is not None:
        fields.append(f"<pubDate>{published}</pubDate>")
    return "<item>" + "".join(fields) + "</item>"


def adapter_for_handler(config: LiveJobSourceConfig, handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return create_live_adapter(config, client=client), client


def ingest(adapter):
    return LiveJobIngestionService.ingest_adapter(adapter, SourceAdapterRegistry([adapter]))


def test_smartrecruiters_detail_preserves_public_urls_timestamps_and_explicit_facts():
    config = source_config("smartrecruiters", max_postings=1)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/postings"):
            return httpx.Response(200, json={"content": [smart_listing_job()]})
        assert request.url.path.endswith("/postings/sr-101")
        return httpx.Response(200, json=smart_detail())

    adapter, client = adapter_for_handler(config, handler)
    try:
        record = adapter.fetch()[0]
    finally:
        client.close()

    assert len(requests) == 2
    assert record.external_id == "sr-101"
    assert record.source_url == "https://jobs.smartrecruiters.com/acme/sr-101"
    assert record.application_url == "https://apply.smartrecruiters.com/acme/sr-101"
    assert record.description == "Build platforms. Learn quickly."
    assert record.locations == ("Denver, CO, US",)
    assert record.employment_type == "INTERNSHIP"
    assert record.work_mode == "REMOTE"
    assert record.posted_at == datetime(2026, 9, 1, 9, 30, tzinfo=timezone.utc)
    assert record.source_updated_at == datetime(2026, 9, 2, 9, 30, tzinfo=timezone.utc)


def test_smartrecruiters_uses_bounded_offset_pagination():
    config = source_config("smartrecruiters", max_postings=30)
    offsets: list[str] = []

    def provider_record(index: int) -> dict[str, object]:
        identifier = f"sr-{index}"
        return smart_listing_job(
            identifier,
            postingUrl=f"https://jobs.smartrecruiters.com/acme/{identifier}",
            applyUrl=f"https://apply.smartrecruiters.com/acme/{identifier}",
        )

    def handler(request: httpx.Request) -> httpx.Response:
        offsets.append(request.url.params["offset"])
        offset = int(request.url.params["offset"])
        return httpx.Response(
            200,
            json={"content": [provider_record(index) for index in range(offset, min(offset + 25, 30))]},
        )

    adapter, client = adapter_for_handler(config, handler)
    try:
        result = adapter.fetch_with_metadata()
    finally:
        client.close()

    assert offsets == ["0", "25"]
    assert len(result.records) == result.fetched_records == 30
    assert not result.complete_listing


def test_smartrecruiters_malformed_posting_does_not_block_a_valid_batch_item():
    config = source_config("smartrecruiters", max_postings=2)
    valid = smart_listing_job(
        "sr-valid",
        postingUrl="https://jobs.smartrecruiters.com/acme/sr-valid",
        applyUrl="https://apply.smartrecruiters.com/acme/sr-valid",
    )
    malformed = smart_listing_job(
        "sr-bad",
        name=42,
        postingUrl="https://jobs.smartrecruiters.com/acme/sr-bad",
        applyUrl="https://apply.smartrecruiters.com/acme/sr-bad",
    )
    adapter, client = adapter_for_handler(
        config,
        lambda _request: httpx.Response(200, json={"content": [valid, malformed]}),
    )
    try:
        result = adapter.fetch_with_metadata()
    finally:
        client.close()

    assert (result.fetched_records, result.skipped_records, len(result.records)) == (2, 1, 1)
    assert result.records[0].external_id == "sr-valid"


def test_rss_and_atom_preserve_explicit_apply_links_and_leave_unknowns_unknown():
    rss_config = source_config("rss")
    rss_adapter, rss_client = adapter_for_handler(
        rss_config, lambda _request: httpx.Response(200, content=rss_document(rss_item()))
    )
    atom_config = source_config("rss", key="rss.atom")
    atom = b"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>atom-101</id><title>Graduate Developer</title>
        <link rel="alternate" href="https://jobs.acme.example/atom-101"/>
        <link rel="apply" href="https://apply.acme.example/atom-101"/>
        <category term="New Graduate"/>
      </entry>
    </feed>"""
    atom_adapter, atom_client = adapter_for_handler(
        atom_config, lambda _request: httpx.Response(200, content=atom)
    )
    try:
        rss = rss_adapter.fetch()[0]
        atom_record = atom_adapter.fetch()[0]
    finally:
        rss_client.close()
        atom_client.close()

    assert rss.application_url == "https://apply.acme.example/feed-101"
    assert rss.employment_type == "CO_OP"
    assert rss.description == "Build reliable services."
    assert atom_record.external_id == "atom-101"
    assert atom_record.application_url == "https://apply.acme.example/atom-101"
    assert atom_record.employment_type == "NEW_GRAD"
    assert atom_record.description is None
    assert atom_record.locations == ()
    assert atom_record.posted_at is None


def test_rss_malformed_or_unsafe_item_does_not_block_valid_item_or_traverse_links():
    config = source_config("rss")
    requests: list[str] = []
    payload = rss_document(
        rss_item("bad-1", link="javascript:alert(1)"),
        rss_item("good-1", link="https://jobs.acme.example/good-1"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(200, content=payload)

    adapter, client = adapter_for_handler(config, handler)
    try:
        result = adapter.fetch_with_metadata()
    finally:
        client.close()

    assert (result.fetched_records, result.skipped_records, len(result.records)) == (2, 1, 1)
    assert result.records[0].external_id == "good-1"
    assert requests == ["https://careers.acme.example/jobs.xml"]


def test_rss_rejects_malformed_xml_and_unconfigured_job_hosts():
    config = source_config("rss")
    malformed, malformed_client = adapter_for_handler(
        config, lambda _request: httpx.Response(200, content=b"<rss><channel>")
    )
    unsafe, unsafe_client = adapter_for_handler(
        config,
        lambda _request: httpx.Response(
            200,
            content=rss_document(rss_item(link="https://other.example/role")),
        ),
    )
    try:
        with pytest.raises(LiveSourceFetchError, match="malformed XML"):
            malformed.fetch()
        result = unsafe.fetch_with_metadata()
    finally:
        malformed_client.close()
        unsafe_client.close()

    assert result.records == ()
    assert result.skipped_records == 1


def test_source_registry_validates_public_configuration_and_priority_policy():
    smart = source_config(
        "smartrecruiters", polling_tier="high", poll_interval_seconds=None
    )
    feed = source_config(
        "rss",
        key="rss.official",
        source_authority="OFFICIAL_COMPANY",
        polling_tier="low",
        poll_interval_seconds=None,
    )
    configs = load_live_source_configs(json.dumps([smart.model_dump(), feed.model_dump()]))
    service = LiveCollectionService(configs, default_timeout_seconds=10, max_concurrency=1)

    assert smart.collection_method == "PUBLIC_JSON_API"
    assert feed.collection_method == "RSS_ATOM"
    assert feed.effective_source_authority == "OFFICIAL_COMPANY"
    assert service.normal_poll_interval_seconds(smart) == 450
    assert service.normal_poll_interval_seconds(feed) == 3600
    with pytest.raises(LiveSourceConfigurationError):
        load_live_source_configs(
            json.dumps(
                [
                    {
                        "key": "rss.local",
                        "family": "rss",
                        "company": "Acme",
                        "feed_url": "https://localhost/jobs.xml",
                    }
                ]
            )
        )
    with pytest.raises(ValueError, match="max_postings"):
        source_config("smartrecruiters", max_postings=51)


def test_new_families_feed_existing_canonical_dedup_authority_and_public_jobs_api(
    isolated_database,
):
    smart_config = source_config("smartrecruiters", max_postings=1)

    def smart_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/postings"):
            return httpx.Response(200, json={"content": [smart_listing_job()]})
        return httpx.Response(
            200,
            json=smart_detail(
                applyUrl="https://apply.acme.example/shared-role",
                jobAd={"sections": {"jobDescription": {"text": "Official role description."}}},
            ),
        )

    smart, smart_client = adapter_for_handler(smart_config, smart_handler)
    feed_config = source_config("rss")
    feed, feed_client = adapter_for_handler(
        feed_config,
        lambda _request: httpx.Response(
            200,
            content=rss_document(
                rss_item(
                    "feed-shared",
                    title="Platform Engineering Intern",
                    link="https://jobs.acme.example/shared-role",
                    apply_url="https://apply.acme.example/shared-role",
                    description="Less authoritative description.",
                    employment_type="Internship",
                    location="Denver, CO, US",
                )
            ),
        ),
    )
    try:
        smart_result = ingest(smart)
        feed_result = ingest(feed)
    finally:
        smart_client.close()
        feed_client.close()

    assert (smart_result.new_canonical_jobs, smart_result.official_apply_urls) == (1, 1)
    assert (feed_result.new_canonical_jobs, feed_result.duplicate_contributions) == (0, 1)
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 1
    assert isolated_database.scalar(select(func.count()).select_from(JobSourceObservation)) == 2
    assert isolated_database.scalar(select(NormalizedJob.description)) == "Official role description."

    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"source-coverage-{uuid4().hex}@example.com", "password": "Password123!"},
    )
    assert response.status_code == 201
    listing = client.get("/api/v1/jobs?keyword=Platform")
    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 1
    assert listing.json()["items"][0]["source_name"] == "SmartRecruiters"


def test_rss_collector_uses_existing_scheduler_health_idempotency_and_value_metrics(
    isolated_database, monkeypatch
):
    config = source_config("rss")
    clock = Clock()
    clients: list[httpx.Client] = []

    def factory(received_config: LiveJobSourceConfig, *, timeout_seconds: float):
        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, content=rss_document(rss_item()))
            )
        )
        clients.append(client)
        return create_live_adapter(received_config, timeout_seconds=timeout_seconds, client=client)

    monkeypatch.setattr(collection_module, "create_live_adapter", factory)
    service = LiveCollectionService(
        (config,),
        default_timeout_seconds=10,
        max_concurrency=1,
        now=clock,
        jitter=lambda *_: 0,
    )
    try:
        service.run_cycle(force=True)
        clock.advance(300)
        service.run_cycle(force=True)
    finally:
        for client in clients:
            client.close()

    row = isolated_database.execute(
        select(
            LiveSourceState.health,
            LiveSourceState.total_collection_attempts,
            LiveSourceState.total_collection_failures,
            LiveSourceState.total_jobs_observed,
            LiveSourceState.total_jobs_ingested,
            LiveSourceState.total_new_canonical_jobs,
            LiveSourceState.total_duplicate_contributions,
            LiveSourceState.total_internship_or_coop_contributions,
            LiveSourceState.total_official_apply_urls,
            LiveSourceState.last_new_canonical_job_at,
        ).where(LiveSourceState.source_key == config.key)
    ).one()
    assert row == (
        LiveSourceHealth.HEALTHY,
        2,
        0,
        2,
        2,
        1,
        0,
        1,
        0,
        NOW,
    )
    assert isolated_database.scalar(select(func.count()).select_from(JobSourceRecord)) == 1
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 1


def test_smartrecruiters_failure_is_isolated_and_recorded_in_existing_health_state(
    isolated_database, monkeypatch
):
    config = source_config("smartrecruiters", max_postings=1)
    clients: list[httpx.Client] = []

    def factory(received_config: LiveJobSourceConfig, *, timeout_seconds: float):
        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(429, json={"detail": "slow down"})
            )
        )
        clients.append(client)
        return create_live_adapter(received_config, timeout_seconds=timeout_seconds, client=client)

    monkeypatch.setattr(collection_module, "create_live_adapter", factory)
    try:
        cycle = LiveCollectionService(
            (config,),
            default_timeout_seconds=10,
            max_concurrency=1,
            now=Clock(),
            jitter=lambda *_: 0,
        ).run_cycle(force=True)
    finally:
        for client in clients:
            client.close()

    assert cycle.failed == 1
    row = isolated_database.execute(
        select(
            LiveSourceState.health,
            LiveSourceState.total_collection_attempts,
            LiveSourceState.total_collection_failures,
        ).where(LiveSourceState.source_key == config.key)
    ).one()
    assert row == (LiveSourceHealth.RATE_LIMITED, 1, 1)
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 0


def test_new_source_ingestion_never_mutates_candidate_owned_data(isolated_database):
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
    adapter, client = adapter_for_handler(
        source_config("rss"),
        lambda _request: httpx.Response(200, content=rss_document(rss_item())),
    )
    try:
        result = ingest(adapter)
    finally:
        client.close()
    after = {
        table.name: isolated_database.scalar(select(func.count()).select_from(table)) for table in tables
    }

    assert result.ingested == 1
    assert after == before
