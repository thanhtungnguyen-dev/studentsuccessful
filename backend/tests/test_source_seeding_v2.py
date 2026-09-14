"""Offline source corpus/import and secondary-observation contracts."""

import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.intelligence import SourceDiscoveryWork, SourceRegistry
from backend.app.models.job import (
    JobSourceObservation,
    JobSourceRecord,
    NormalizedJob,
    RawJobSnapshot,
)
from backend.app.services.aggregator_observations import import_observations
from backend.app.services.canonical_jobs import supplemental_metadata
from backend.app.services.source_intelligence import effective_sources
from backend.app.services.source_seeds import DEFAULT_SEEDS, import_seeds, load_seeds


def write_json(tmp_path, value):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_corpus_static_and_diverse():
    seeds = load_seeds()
    assert len(seeds) >= 180
    assert len({(c.family, c.key) for c in seeds}) == len(seeds)
    assert {c.family for c in seeds} == {
        "greenhouse",
        "lever",
        "ashby",
        "smartrecruiters",
        "workable",
        "teamtailor",
        "recruitee",
        "personio",
    }


@pytest.mark.parametrize(
    "change", ["provider", "duplicate_key", "duplicate_identity", "unsafe", "noncanonical", "order"]
)
def test_invalid_corpus_rejected(tmp_path, change):
    rows = json.loads(DEFAULT_SEEDS.read_text())[:2]
    if change == "provider":
        rows[0]["provider"] = "workday"
    if change == "duplicate_key":
        rows[1]["key"] = rows[0]["key"]
    if change == "duplicate_identity":
        rows[1].update(url=rows[0]["url"], provider=rows[0]["provider"])
    if change == "unsafe":
        rows[0]["url"] = "https://user:secret@example.com/path"
    if change == "noncanonical":
        rows[0]["url"] += "?token=secret"
    if change == "order":
        rows.reverse()
    with pytest.raises(ValueError):
        load_seeds(write_json(tmp_path, rows))


def test_import_idempotent_dry_run_preserves_discovered_and_runtime(tmp_path, isolated_database):
    rows = json.loads(DEFAULT_SEEDS.read_text())[:2]
    path = write_json(tmp_path, rows)
    config = load_seeds(path)[0]
    from backend.app.ingestion.source_detection import source_identity

    with Session(isolated_database) as session:
        session.add(
            SourceRegistry(
                source_key="existing",
                provider=config.family,
                identity=source_identity(config),
                configuration=config.model_copy(
                    update={"key": "existing", "company": "Old name", "max_postings": 7}
                ).model_dump(mode="json"),
                origin="DISCOVERED",
                enabled=False,
            )
        )
        session.commit()
    dry = import_seeds(path, dry_run=True)
    assert dry["new"] == 1 and dry["updated"] == 1
    with Session(isolated_database) as session:
        assert session.scalar(select(func.count()).select_from(SourceRegistry)) == 1
    assert import_seeds(path)["new"] == 1
    assert import_seeds(path)["new"] == 0
    with Session(isolated_database) as session:
        old = session.get(SourceRegistry, "existing")
        assert not old.enabled and old.configuration["max_postings"] == 7
        assert (
            old.configuration["key"] == "existing"
            and old.configuration["company"] == config.company
        )
        assert session.scalar(select(func.count()).select_from(SourceRegistry)) == 2
    assert len(effective_sources(())) == 2


def observation(provider, **updates):
    source = provider
    host = {
        "linkedin": "www.linkedin.com",
        "indeed": "www.indeed.com",
        "intern_insider": "interninsider.example.org",
    }[source]
    row = dict(
        source=source,
        external_id="posting-1",
        listing_url=f"https://{host}/jobs/posting-1",
        apply_url="https://boards.greenhouse.io/acme/jobs/123",
        company="Acme LLC",
        title="Software Engineer Intern",
        location="Toronto, Canada",
        employment_type="INTERNSHIP",
        metadata={"term": "Summer 2027", "deadline": "2026-10-01", "posted_text": "2 days ago"},
    )
    row.update(updates)
    return row


@pytest.mark.parametrize("source", ["linkedin", "indeed", "intern_insider"])
def test_secondary_import_idempotent_provenance_and_discovery(source, tmp_path, isolated_database):
    path = write_json(tmp_path, [observation(source)])
    assert import_observations(path)["observations"] == 1
    import_observations(path)
    with Session(isolated_database) as session:
        assert session.scalar(select(func.count()).select_from(NormalizedJob)) == 1
        assert session.scalar(select(func.count()).select_from(JobSourceRecord)) == 1
        assert session.scalar(select(func.count()).select_from(RawJobSnapshot)) == 1
        job = session.scalar(select(NormalizedJob))
        assert job.application_url == "https://boards.greenhouse.io/acme/jobs/123"
        assert job.posted_at is None
        obs = session.scalar(select(JobSourceObservation))
        assert supplemental_metadata([obs])["term"]["value"] == "Summer 2027"
        work = session.scalar(select(SourceDiscoveryWork))
        assert work.url == "https://boards.greenhouse.io/acme"
        assert work.parent_source == source


def test_three_secondary_sources_and_official_one_canonical(tmp_path, isolated_database):
    from backend.app.core.unit_of_work import UnitOfWork
    from backend.app.ingestion.adapters import SourceAdapterRegistry
    from backend.app.ingestion.aggregators import StructuredObservationAdapter
    from backend.app.ingestion.dto import ExternalJobDTO, ExternalJobMetadata
    from backend.app.repositories.live_job_ingestion import LiveJobIngestionRepository
    from backend.app.services.job_ingestion import JobIngestionService

    path = write_json(tmp_path, [observation(s) for s in ("linkedin", "indeed", "intern_insider")])
    import_observations(path)
    adapter = StructuredObservationAdapter("linkedin")
    adapter.key, adapter.source_authority = "official", "OFFICIAL_ATS"
    registry = SourceAdapterRegistry([adapter])
    record = ExternalJobDTO(
        adapter_key="official",
        external_id="123",
        source_url="https://boards.greenhouse.io/acme/jobs/123",
        application_url="https://boards.greenhouse.io/acme/jobs/123",
        company="Acme LLC",
        title="Official title",
        role="Unspecified",
        employment_type="INTERNSHIP",
        locations=("Calgary, Canada",),
        metadata=ExternalJobMetadata(deadline="2026-09-30"),
    )
    with UnitOfWork() as uow:
        LiveJobIngestionRepository(uow.session).ensure_configured_catalog("Acme", record.role)
        uow.session.flush()
        JobIngestionService.ingest(record, registry, uow)
    import_observations(path)
    with Session(isolated_database) as session:
        assert session.scalar(select(func.count()).select_from(NormalizedJob)) == 1
        job = session.scalar(select(NormalizedJob))
        assert job.title == "Official title"
        observations = session.scalars(select(JobSourceObservation)).all()
        assert len(observations) == 4
        metadata = supplemental_metadata(observations)
        assert metadata["deadline"]["value"] == "2026-09-30"
        assert metadata["term"]["value"] == "Summer 2027"
        assert "sponsorship" not in metadata
        assert metadata["deadline"]["observation_id"] != metadata["term"]["observation_id"]
        assert job.field_provenance["metadata.term"] == metadata["term"]["observation_id"]
        assert job.is_active


@pytest.mark.parametrize(
    "field,value",
    [
        ("source", "unknown"),
        ("listing_url", "https://evil.com/jobs/1"),
        ("posted_at", "2 days ago"),
        ("apply_url", "https://127.0.0.1/private"),
        ("apply_url", "https://example.org/?token=secret"),
    ],
)
def test_bad_observation_rejected(tmp_path, field, value):
    with pytest.raises(ValueError):
        import_observations(write_json(tmp_path, [observation("linkedin", **{field: value})]))


def test_same_title_without_strong_identity_does_not_merge(tmp_path, isolated_database):
    rows = [observation("linkedin", apply_url=None), observation("indeed", apply_url=None)]
    import_observations(write_json(tmp_path, rows))
    with Session(isolated_database) as session:
        assert session.scalar(select(func.count()).select_from(NormalizedJob)) == 2


@pytest.mark.parametrize(
    "left,right",
    [
        (
            "https://job-boards.greenhouse.io/acme/jobs/123?utm_source=x",
            "https://boards.greenhouse.io/acme/jobs/123",
        ),
        ("https://jobs.ashbyhq.com/acme/abc/application", "https://jobs.ashbyhq.com/acme/abc"),
        ("https://jobs.lever.co/acme/abc/apply", "https://jobs.lever.co/acme/abc"),
    ],
)
def test_apply_alias_identity(left, right):
    from backend.app.services.canonical_jobs import canonical_url_fingerprint

    assert canonical_url_fingerprint(left) == canonical_url_fingerprint(right)


@pytest.mark.parametrize("source", ["linkedin", "indeed", "intern_insider"])
def test_official_first_secondary_absence_and_closed_authority(source, tmp_path, isolated_database):
    from backend.app.models.job import JobLifecycle
    from backend.tests.test_canonical_jobs import (
        ingest,
        reconcile_successful_source,
        record,
        seed_catalog,
    )

    seed_catalog(isolated_database)
    url = "https://boards.greenhouse.io/acme/jobs/123"
    item = record(
        adapter_key="official", source_url=url, application_url=url, title="Official title"
    )
    job_id = ingest(item, "OFFICIAL_ATS")
    path = write_json(tmp_path, [observation(source)])
    import_observations(path)
    for _ in range(4):
        reconcile_successful_source(source, ())
    with Session(isolated_database) as session:
        assert session.scalar(select(func.count()).select_from(NormalizedJob)) == 1
        job = session.get(NormalizedJob, job_id)
        assert job.is_active and job.title == "Official title"
        secondary = session.scalar(
            select(JobSourceObservation)
            .join(JobSourceRecord)
            .where(JobSourceRecord.source_adapter == source)
        )
        assert secondary.consecutive_absent_successes == 0
    ingest(item.model_copy(update={"source_status": "CLOSED"}), "OFFICIAL_ATS")
    import_observations(path)
    with Session(isolated_database) as session:
        assert session.get(NormalizedJob, job_id).lifecycle == JobLifecycle.CLOSED


def test_unknown_metadata_stays_missing():
    from backend.app.ingestion.dto import ExternalJobMetadata

    fields = ExternalJobMetadata(deadline="UNKNOWN", term=" ", sponsorship="unspecified")
    assert fields.model_dump(exclude_none=True) == {}


@pytest.mark.parametrize(
    "url",
    [
        "https://boards.greenhouse.io/acme",
        "https://job-boards.greenhouse.io/acme?utm_source=listing",
        "https://example.org/job?access%5Ftoken=secret",
    ],
)
def test_unsafe_or_board_apply_url_rejected(tmp_path, url):
    with pytest.raises(ValueError):
        import_observations(write_json(tmp_path, [observation("linkedin", apply_url=url)]))


def test_conflicting_official_posting_ids_do_not_merge(tmp_path, isolated_database):
    rows = [
        observation("linkedin"),
        observation("indeed", apply_url="https://boards.greenhouse.io/acme/jobs/456"),
    ]
    import_observations(write_json(tmp_path, rows))
    with Session(isolated_database) as session:
        assert session.scalar(select(func.count()).select_from(NormalizedJob)) == 2


def test_aggregator_discovery_then_seed_reuses_verified_identity(tmp_path, isolated_database):
    from types import SimpleNamespace

    from backend.app.services.source_intelligence import process_discovery

    import_observations(write_json(tmp_path, [observation("linkedin")]))
    seen = []

    def adapter(config, **kwargs):
        seen.append(config)
        return SimpleNamespace(
            fetch_with_metadata=lambda: SimpleNamespace(skipped_records=0, not_modified=False)
        )

    assert process_discovery(adapter_factory=adapter) == ["VERIFIED"]
    assert len(seen) == 1 and seen[0].board_token == "acme"
    rows = [
        dict(
            key="acme-seed",
            company="Acme",
            provider="greenhouse",
            url="https://boards.greenhouse.io/acme",
            evidence="fixture",
            geography="Canada",
        )
    ]
    assert import_seeds(write_json(tmp_path, rows))["existing"] == 1
    with Session(isolated_database) as session:
        assert session.scalar(select(func.count()).select_from(SourceRegistry)) == 1
    assert len(effective_sources(())) == 1


def test_full_corpus_import_preserves_runtime_and_collector_consumes(tmp_path, isolated_database):
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    from backend.app.models.job import LiveSourceState
    from backend.app.services.live_collection import LiveCollectionService

    rows = [
        dict(
            key="unrelated",
            company="Fixture",
            provider="greenhouse",
            url="https://boards.greenhouse.io/fixture",
            evidence="fixture",
            geography="Other/Unknown",
        )
    ]
    import_seeds(write_json(tmp_path, rows))
    first = load_seeds()[0]
    lease = uuid4()
    clock = datetime.now(timezone.utc)
    with Session(isolated_database) as session:
        session.add(
            LiveSourceState(
                source_key=first.key,
                source_family=first.family,
                normal_poll_interval_seconds=3600,
                health="DEGRADED",
                consecutive_failures=2,
                retrieval_cursor="retained-cursor",
                lease_token=lease,
                lease_expires_at=clock + timedelta(minutes=5),
                next_poll_at=clock + timedelta(hours=1),
                total_collection_attempts=10,
            )
        )
        session.commit()
    assert import_seeds(dry_run=True)["new"] == len(load_seeds())
    first_result = import_seeds()
    assert first_result == dict(
        new=len(load_seeds()), existing=0, updated=0, skipped=0, invalid=0, duplicate=0
    )
    assert import_seeds() == dict(
        new=0, existing=len(load_seeds()), updated=0, skipped=0, invalid=0, duplicate=0
    )
    with Session(isolated_database) as session:
        state = session.scalar(
            select(LiveSourceState).where(LiveSourceState.source_key == first.key)
        )
        assert (
            state.health,
            state.consecutive_failures,
            state.retrieval_cursor,
            state.lease_token,
        ) == ("DEGRADED", 2, "retained-cursor", lease)
        assert state.total_collection_attempts == 10
        assert session.get(SourceRegistry, "unrelated").enabled
    service = LiveCollectionService((), default_timeout_seconds=10)
    service.synchronize()
    assert {c.key for c in service.configs} == {c.key for c in load_seeds()} | {"unrelated"}


def test_official_absence_not_overridden_by_secondary_positive(tmp_path, isolated_database):
    from backend.app.core.config import settings
    from backend.app.models.job import JobLifecycle
    from backend.tests.test_canonical_jobs import (
        ingest,
        reconcile_successful_source,
        record,
        seed_catalog,
    )

    seed_catalog(isolated_database)
    url = "https://boards.greenhouse.io/acme/jobs/123"
    job_id = ingest(
        record(adapter_key="official", source_url=url, application_url=url), "OFFICIAL_ATS"
    )
    path = write_json(tmp_path, [observation("intern_insider")])
    import_observations(path)
    for _ in range(max(2, settings.JOB_CLOSE_AFTER_SUCCESSFUL_ABSENCES)):
        reconcile_successful_source("official", ())
    import_observations(path)
    with Session(isolated_database) as session:
        assert session.get(NormalizedJob, job_id).lifecycle == JobLifecycle.CLOSED
