"""Offline scope rules and pre-write policy boundaries."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from backend.app.ingestion.dto import ExternalJobDTO
from backend.app.ingestion.job_scope import classify_job
from backend.app.models.job import NormalizedJob
from backend.app.models.taxonomy import Company


def job(**updates):
    values = dict(
        adapter_key="fixture",
        external_id="1",
        source_url="https://example.org/jobs/1",
        application_url="https://example.org/jobs/1",
        company="Scope Fixture",
        title="Software Engineer",
        role="Unspecified",
        employment_type="UNSPECIFIED",
        locations=("Toronto, ON",),
    )
    values.update(updates)
    return ExternalJobDTO(**values)


@pytest.mark.parametrize(
    "location",
    [
        "Toronto, ON",
        "Vancouver, BC",
        "Calgary, AB",
        "Waterloo, ON",
        "Montréal, QC",
        "Seattle, WA",
        "San Francisco, CA",
        "New York, NY",
        "Austin, TX",
        "Remote Canada",
        "Canada Remote",
        "Remote - United States",
        "Remote US",
        "Remote North America",
        "Canada",
        "USA",
        "U.S.",
        "California",
        "Texas",
    ],
)
def test_geography_keep(location):
    assert classify_job(job(locations=(location,))).accepted


@pytest.mark.parametrize(
    "location",
    [
        "London",
        "Berlin",
        "Singapore",
        "Taipei",
        "Remote Worldwide",
        "Remote",
        "",
        "London, ON, UK",
        "Toronto, Germany",
        "Cambridge",
        "Austin, TX, UK",
    ],
)
def test_geography_drop(location):
    assert not classify_job(job(locations=(location,))).accepted


def test_multi_location_accepts_explicit_supported_city():
    assert classify_job(job(locations=("London", "Toronto"))).accepted


@pytest.mark.parametrize(
    "title",
    [
        "Software Engineer",
        "Software Engineer Intern",
        "Software Developer Co-op",
        "Backend Engineer",
        "Frontend Engineer",
        "Full Stack Engineer",
        "Mobile Engineer",
        "Data Engineer",
        "Data Scientist",
        "ML Engineer",
        "AI Engineer",
        "Computer Vision Engineer",
        "Security Engineer",
        "SRE",
        "DevOps Engineer",
        "Embedded Software Engineer",
        "Firmware Engineer",
        "Systems Engineer",
        "Database Engineer",
        "Compiler Engineer",
        "Networking Engineer",
        "HPC Engineer",
        "Robotics Engineer",
        "SDET",
        "QA Automation Engineer",
        "Quant Developer",
        "Platform Engineering Intern",
        "Senior Software Engineer",
        "Staff Software Engineer",
        "ML Intern",
    ],
)
def test_technical_keep(title):
    assert classify_job(job(title=title)).accepted


@pytest.mark.parametrize(
    "title",
    [
        "Marketing Intern",
        "HR Intern",
        "Sales Intern",
        "Accounting Co-op",
        "Recruiter",
        "Campus Recruiter",
        "Operations Intern",
        "Legal Intern",
        "Financial Analyst Intern",
        "Solutions Engineer - Sales",
        "Software Engineering Recruiter",
        "Data Analyst Intern",
    ],
)
def test_nontechnical_drop(title):
    assert not classify_job(job(title=title)).accepted


def test_data_analyst_requires_explicit_technical_evidence():
    assert classify_job(
        job(title="Data Analyst Intern", description="Build SQL data pipelines using Python.")
    ).accepted


@pytest.mark.parametrize(
    "employment,level,priority",
    [
        ("INTERNSHIP", "STUDENT", "VERY_HIGH"),
        ("CO_OP", "STUDENT", "VERY_HIGH"),
        ("NEW_GRAD", "ENTRY", "HIGH"),
        ("FULL_TIME", "UNSPECIFIED", "NORMAL"),
        ("PART_TIME", "UNSPECIFIED", "LOWER"),
        ("CONTRACT", "UNSPECIFIED", "LOWER"),
        ("FULL_TIME", "SENIOR", "LOWER"),
        ("FULL_TIME", "STAFF", "LOWER"),
    ],
)
def test_priority_never_discards_technical_jobs(employment, level, priority):
    d = classify_job(job(employment_type=employment, career_level=level))
    assert d.accepted and d.priority == priority


def test_live_scope_filters_before_catalog_and_hash(monkeypatch):
    from backend.app.ingestion.live import LiveFetchResult
    from backend.app.services import source_intelligence
    from backend.app.services.live_job_ingestion import LiveJobIngestionService

    monkeypatch.setattr(source_intelligence, "preserve_fetch", lambda *a: None)

    def forbidden():
        raise AssertionError("Out-of-scope records must not open an ingestion UoW")

    adapter = SimpleNamespace(key="fixture", family="greenhouse")

    def run(record):
        return LiveJobIngestionService.ingest_adapter(
            adapter,
            None,
            fetch_result=LiveFetchResult(
                records=(record,),
                fetched_records=1,
                complete_listing=True,
                skipped_records=0,
                filtered_records=0,
                not_modified=False,
                http_status=200,
                etag=None,
                last_modified=None,
            ),
            uow_factory=forbidden,
        )

    first = run(job(locations=("Berlin",)))
    second = run(job(title="Marketing Intern", locations=("Singapore",)))
    assert first.scope_filtered == 1 and first.parsed == first.ingested == 0
    assert first.content_hash == second.content_hash
    from backend.app.services.live_collection import LiveCollectionService

    assert LiveCollectionService._safe_for_lifecycle_reconciliation(first)


@pytest.mark.parametrize("source", ["linkedin", "indeed", "intern_insider"])
def test_aggregator_scope_before_any_uow(source, tmp_path):
    from backend.app.services.aggregator_observations import import_observations
    from backend.tests.test_source_seeding_v2 import observation

    path = tmp_path / "rows.json"
    path.write_text(json.dumps([observation(source, location="Singapore")]))

    def forbidden():
        raise AssertionError("No per-record DB work")

    assert import_observations(path, uow_factory=forbidden) == {
        "observations": 0,
        "scope_filtered": 1,
    }


def test_discovery_drops_irrelevant_before_transaction():
    from backend.app.services.source_intelligence import enqueue_urls

    def forbidden():
        raise AssertionError("No discovery transaction")

    enqueue_urls((job(locations=("Singapore",)),), "fixture", forbidden)


def test_scoped_live_hash_and_lifecycle(isolated_database):
    from backend.app.core.config import settings
    from backend.app.models.job import JobLifecycle
    from backend.tests.test_canonical_jobs import reconcile_successful_source
    from backend.tests.test_live_job_ingestion import (
        greenhouse_job,
        greenhouse_payload,
        ingest,
        source_config,
    )

    config = source_config("greenhouse")
    good = greenhouse_job(title="Software Engineer", location={"name": "Seattle, WA"})
    irrelevant = greenhouse_job(id=999, title="Marketing Intern", location={"name": "Berlin"})
    first = ingest(config, greenhouse_payload(good, irrelevant))
    second = ingest(config, greenhouse_payload(good, dict(irrelevant, content="Global change")))
    assert first.ingested == 1 and first.scope_filtered == 1
    assert first.content_hash == second.content_hash
    third = ingest(config, greenhouse_payload(dict(good, content="Relevant change"), irrelevant))
    assert third.content_hash != second.content_hash
    empty = ingest(config, greenhouse_payload(irrelevant))
    for _ in range(max(2, settings.JOB_CLOSE_AFTER_SUCCESSFUL_ABSENCES)):
        reconcile_successful_source(config.key, empty.observed_external_ids)
    assert isolated_database.scalar(select(NormalizedJob.lifecycle)) == JobLifecycle.CLOSED


def test_global_board_no_catalog_when_all_filtered(isolated_database):
    from backend.tests.test_live_job_ingestion import (
        greenhouse_job,
        greenhouse_payload,
        ingest,
        source_config,
    )

    result = ingest(
        source_config("greenhouse"), greenhouse_payload(greenhouse_job(location={"name": "Berlin"}))
    )
    assert result.scope_filtered == 1
    assert isolated_database.scalar(select(func.count()).select_from(Company)) == 0
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 0


def test_large_board_only_twenty_records_enter_ingestion(monkeypatch):
    from backend.app.core.config import settings
    from backend.app.ingestion.live import LiveFetchResult
    from backend.app.services import live_job_ingestion, source_intelligence
    from backend.app.services.live_job_ingestion import LiveJobIngestionService

    monkeypatch.setattr(source_intelligence, "preserve_fetch", lambda *a: None)
    monkeypatch.setattr(settings, "LIVE_SOURCE_DISCOVERY_ENABLED", True)
    written, catalog, queued = [], [], []

    class Uow:
        session = None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def commit(self):
            pass

    monkeypatch.setattr(
        live_job_ingestion.LiveJobIngestionRepository,
        "ensure_configured_catalog",
        lambda self, *args: catalog.append(args),
    )

    def ingest(record, *args):
        written.append(record)
        return SimpleNamespace(source_observation_created=True, canonical_created=True)

    monkeypatch.setattr(live_job_ingestion.JobIngestionService, "ingest_with_outcome", ingest)
    monkeypatch.setattr(
        source_intelligence, "enqueue_urls", lambda records, *args: queued.extend(records)
    )
    records = tuple(
        job(external_id=str(i), locations=("Toronto, ON" if i < 20 else "Berlin",))
        for i in range(1000)
    )
    result = LiveJobIngestionService.ingest_adapter(
        SimpleNamespace(
            key="fixture",
            family="greenhouse",
            config=SimpleNamespace(company="Scope Fixture"),
            source_authority="OFFICIAL_ATS",
        ),
        None,
        fetch_result=LiveFetchResult(
            records=records,
            fetched_records=1000,
            skipped_records=0,
            filtered_records=0,
            not_modified=False,
            http_status=200,
            etag=None,
            last_modified=None,
            complete_listing=True,
        ),
        uow_factory=Uow,
    )
    assert result.scope_filtered == 980 and result.ingested == 20 and result.jobs_ca == 20
    assert len(written) == len(queued) == 20 and len(catalog) == 1
    assert result.observed_external_ids == tuple(str(i) for i in range(20))


def test_malformed_still_blocks_absence_after_scope_filtering():
    from backend.app.services.live_collection import LiveCollectionService
    from backend.app.services.live_job_ingestion import LiveSourceIngestionResult

    result = LiveSourceIngestionResult(
        source_key="fixture",
        family="greenhouse",
        fetched=100,
        parsed=1,
        ingested=1,
        malformed=1,
        rejected=0,
        filtered=0,
        scope_filtered=98,
        complete_listing=True,
    )
    assert not LiveCollectionService._safe_for_lifecycle_reconciliation(result)


def test_official_and_aggregator_share_scope_and_canonical(isolated_database, tmp_path):
    from backend.app.services.aggregator_observations import import_observations
    from backend.tests.test_live_job_ingestion import (
        greenhouse_job,
        greenhouse_payload,
        ingest,
        source_config,
    )
    from backend.tests.test_source_seeding_v2 import observation

    official = greenhouse_job(title="Software Engineer", location={"name": "Toronto, ON"})
    path = tmp_path / "observations.json"
    path.write_text(
        json.dumps(
            [
                observation(
                    "linkedin",
                    title="Software Engineer Intern",
                    apply_url=official["absolute_url"],
                    location="Toronto, ON",
                )
            ]
        )
    )
    import_observations(path)
    ingest(source_config("greenhouse"), greenhouse_payload(official))
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 1
    assert isolated_database.scalar(select(NormalizedJob.title)) == "Software Engineer"


def test_scope_hash_independent_of_empty_batches_and_order():
    from backend.app.services.live_job_ingestion import scoped_content_hash

    relevant = (("one", "content-a"), ("two", "content-b"))
    assert scoped_content_hash(relevant) == scoped_content_hash(tuple(reversed(relevant)))
    assert scoped_content_hash(relevant + ()) == scoped_content_hash(relevant)
    assert scoped_content_hash(relevant) != scoped_content_hash((("one", "changed"), relevant[1]))


def test_applied_scientist_needs_computing_evidence():
    assert not classify_job(
        job(title="Applied Scientist", description="Laboratory chemistry research")
    ).accepted
    assert classify_job(
        job(title="Applied Scientist", description="Machine learning using Python")
    ).accepted
