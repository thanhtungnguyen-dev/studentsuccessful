"""Offline V2 integration over the real disposable PostgreSQL UoW."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select

from backend.app.core.config import settings
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.ingestion.adapters import SourceAdapterRegistry
from backend.app.ingestion.live import (
    LiveJobSourceConfig,
    LiveSourceFetchError,
    _employment_type,
    _work_mode,
    create_live_adapter,
)
from backend.app.ingestion.normalization import structured_location
from backend.app.ingestion.public_http import public_addresses, public_get, public_url
from backend.app.ingestion.source_detection import detect_source, source_identity
from backend.app.ingestion.structured import jsonld_jobs
from backend.app.models.intelligence import (
    JobChangeEvent,
    SourceDiscoveryWork,
    SourceFetchEvidence,
    SourceRegistry,
)
from backend.app.models.job import JobLocation, LiveSourceState, NormalizedJob
from backend.app.services.job_ingestion import normalize_company_identity
from backend.app.services.live_job_ingestion import LiveJobIngestionService
from backend.app.services.source_intelligence import (
    effective_sources,
    enqueue_urls,
    preserve_fetch,
    process_discovery,
    replay_fetch,
)
from backend.app.services.source_quality import adaptive_interval, quality_report
from backend.tests.test_canonical_jobs import ingest, record, seed_catalog


@pytest.mark.parametrize(
    "url,family,identity",
    [
        ("https://jobs.lever.co/acme/123", "lever", "global:acme"),
        ("https://jobs.eu.lever.co/acme/456/apply", "lever", "eu:acme"),
        ("https://boards.greenhouse.io/acme/jobs/123", "greenhouse", "acme"),
        ("https://job-boards.greenhouse.io/acme/jobs/456", "greenhouse", "acme"),
        ("https://boards-api.greenhouse.io/v1/boards/acme/jobs", "greenhouse", "acme"),
        ("https://jobs.ashbyhq.com/acme/123", "ashby", "acme"),
        ("https://jobs.smartrecruiters.com/acme/123", "smartrecruiters", "acme"),
        ("https://acme.recruitee.com/o/123", "recruitee", "acme.recruitee.com"),
        ("https://acme.jobs.personio.de/job/123", "personio", "acme.jobs.personio.de"),
    ],
)
def test_detection(url, family, identity):
    config = detect_source(url, "Acme")
    assert config.family == family
    assert source_identity(config) == identity


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/x",
        "http://127.0.0.1",
        "http://10.0.0.1",
        "http://169.254.169.254/latest",
        "http://[::1]",
        "http://[fc00::1]",
        "https://user:pass@example.com",
        "file:///etc/passwd",
        "https://example.com:22",
        "https://a.local",
        "https://example.com\\@localhost",
    ],
)
def test_unsafe_url_rejected(url):
    with pytest.raises(ValueError):
        public_url(url)


def test_unknown_is_not_a_provider_guess():
    assert detect_source("https://jobs.lever.co.evil.example/acme/id", "Acme") is None
    assert detect_source("https://employer.example/careers", "Acme") is None


def test_dns_all_answers_must_be_public(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", ("93.184.216.34", 443)), (0, 0, 0, "", ("10.0.0.1", 443))],
    )
    with pytest.raises(ValueError, match="nonpublic"):
        public_addresses("example.com", 443)


def test_redirect_validates_next_hop_before_connect(monkeypatch):
    import backend.app.ingestion.public_http as module

    connections = []

    class Connection:
        def __init__(self, host, *args, **kwargs):
            connections.append(host)

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return SimpleNamespace(
                status=302,
                getheader=lambda key, default=None: (
                    "http://127.0.0.1/private" if key == "Location" else default
                ),
            )

        def close(self):
            pass

    monkeypatch.setattr(module, "public_addresses", lambda *args: ["93.184.216.34"])
    monkeypatch.setattr(module.http.client, "HTTPConnection", Connection)
    monkeypatch.setattr(
        module.socket,
        "create_connection",
        lambda *args, **kwargs: SimpleNamespace(settimeout=lambda *a: None),
    )
    with pytest.raises(ValueError):
        public_get("http://example.com/redirect")
    assert connections == ["example.com"]


def source(family):
    urls = {
        "recruitee": "https://acme.recruitee.com",
        "personio": "https://acme.jobs.personio.de",
        "jsonld": "https://acme.example/careers/job",
    }
    return LiveJobSourceConfig(
        key="v2." + family, family=family, company="Acme", public_board_url=urls[family]
    )


def payload(family):
    if family == "recruitee":
        return json.dumps(
            {
                "offers": [
                    {
                        "id": 123,
                        "title": "SWE Intern",
                        "careers_url": "https://acme.recruitee.com/o/swe",
                        "careers_apply_url": "https://acme.recruitee.com/o/swe/c/new",
                        "description": "<p>Build systems</p>",
                        "locations": [
                            {"city": "Calgary", "state": "Alberta", "country": "Canada"},
                            {"city": "Toronto", "state": "Ontario", "country": "Canada"},
                        ],
                        "published_at": "2026-09-01T00:00:00Z",
                        "employment_type": "internship",
                        "workplace_type": "hybrid",
                    }
                ]
            }
        )
    if family == "personio":
        return "<workzag-jobs><position><id>123</id><name>SWE Intern</name><office>Calgary, AB</office><additionalOffices><office>Toronto, ON</office></additionalOffices><employmentType>internship</employmentType><jobDescriptions><jobDescription><value>Build systems</value></jobDescription></jobDescriptions></position></workzag-jobs>"
    return (
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "JobPosting",
                "title": "SWE Intern",
                "description": "Build systems",
                "hiringOrganization": {"name": "Acme"},
                "url": "https://acme.example/careers/job",
                "employmentType": "internship",
                "jobLocation": [
                    {
                        "address": {
                            "addressLocality": "Calgary",
                            "addressRegion": "Alberta",
                            "addressCountry": "Canada",
                        }
                    },
                    {
                        "address": {
                            "addressLocality": "Toronto",
                            "addressRegion": "Ontario",
                            "addressCountry": "Canada",
                        }
                    },
                ],
            }
        )
        + "</script>"
    )


@pytest.mark.parametrize("family", ["recruitee", "personio", "jsonld"])
def test_provider_happy_path_and_replay(family, isolated_database):
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=payload(family)))
    ) as client:
        adapter = create_live_adapter(source(family), client=client)
        result = adapter.fetch_with_metadata()
        assert len(result.records) == 1
        dto = result.records[0]
        assert dto.title == "SWE Intern"
        assert len(dto.locations) == 2
        assert dto.employment_type == "INTERNSHIP"
        digest = preserve_fetch(adapter)
        replay = replay_fetch(adapter.key, digest)
        assert replay.records == result.records
        assert isolated_database.scalar(select(func.count()).select_from(SourceFetchEvidence)) == 1
        assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 0


@pytest.mark.parametrize("family", ["recruitee", "personio", "jsonld"])
@pytest.mark.parametrize(
    "status,category", [(429, "RATE_LIMITED"), (503, "HTTP_5XX"), (401, "HTTP_ERROR")]
)
def test_provider_http_errors(family, status, category):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(status, headers={"Retry-After": "90"})
        )
    ) as client:
        with pytest.raises(LiveSourceFetchError) as error:
            create_live_adapter(source(family), client=client).fetch()
        assert error.value.category == category
        assert error.value.retry_after_seconds == 90


@pytest.mark.parametrize("family", ["recruitee", "personio", "jsonld"])
def test_provider_timeout_and_malformed(family):
    def timeout(request):
        raise httpx.ReadTimeout("offline timeout")

    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(LiveSourceFetchError, match="timed out"):
            create_live_adapter(source(family), client=client).fetch()
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="not structured data"))
    ) as client:
        with pytest.raises((LiveSourceFetchError, ValueError)):
            create_live_adapter(source(family), client=client).fetch()


@pytest.mark.parametrize(
    "family,body", [("recruitee", '{"offers":[]}'), ("personio", "<workzag-jobs/>")]
)
def test_empty_boards(family, body):
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=body))
    ) as client:
        result = create_live_adapter(source(family), client=client).fetch_with_metadata()
        assert result.records == () and result.complete_listing


def test_jsonld_graph_and_malformed_scripts():
    html = '<script type="application/ld+json">oops</script><script type="application/ld+json">{"@graph":[{"@type":"JobPosting","title":"Real"}]}</script>'
    assert jsonld_jobs(html) == [{"@type": "JobPosting", "title": "Real"}]


def test_discovery_registry_restart_seed_dedup_and_disabled_seed(isolated_database):
    item = record(application_url="https://jobs.lever.co/acme/123")
    enqueue_urls([item, item], "parent")
    # Both source and apply URL are queued once each.
    assert isolated_database.scalar(select(func.count()).select_from(SourceDiscoveryWork)) == 2

    def factory(config, **kwargs):
        return SimpleNamespace(
            fetch_with_metadata=lambda: SimpleNamespace(skipped_records=0, not_modified=False)
        )

    statuses = process_discovery(
        adapter_factory=factory,
        fetch=lambda *a, **k: httpx.Response(200, request=httpx.Request("GET", a[0])),
        limit=3,
    )
    assert "VERIFIED" in statuses
    discovered = effective_sources(())
    assert len(discovered) == 1 and discovered[0].family == "lever"
    seed = discovered[0].model_copy(update={"key": "manual.acme", "enabled": False})
    assert effective_sources((seed,)) == (seed,)
    assert effective_sources((seed, seed)) == (seed,)
    assert isolated_database.scalar(select(func.count()).select_from(SourceRegistry)) == 1


def test_discovery_redirect_and_failure_does_not_touch_jobs(isolated_database):
    enqueue_urls([record(application_url="https://employer.example/redirect")], "parent")
    def factory(config, **kw):
        return SimpleNamespace(
            fetch_with_metadata=lambda: SimpleNamespace(skipped_records=0, not_modified=False)
        )

    def fetch(url, **kw):
        return httpx.Response(200, request=httpx.Request("GET", "https://jobs.lever.co/acme/id"))
    assert process_discovery(fetch=fetch, adapter_factory=factory) == ["VERIFIED", "VERIFIED"]
    assert len(effective_sources(())) == 1
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 0


@pytest.mark.parametrize(
    "base,changed,new,quiet,recovery,expected",
    [
        (900, False, 0, 0, False, 900),
        (900, True, 0, 0, False, 450),
        (900, False, 2, 0, False, 450),
        (900, False, 0, 12, False, 7200),
        (900, True, 2, 0, True, 900),
        (300, True, 1, 0, False, 300),
        (86400, False, 0, 40, False, 86400),
    ],
)
def test_adaptive_bounds(base, changed, new, quiet, recovery, expected):
    assert (
        adaptive_interval(base, changed=changed, new_jobs=new, unchanged=quiet, recovering=recovery)
        == expected
    )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Calgary, AB", ("CA", "Alberta", "Calgary")),
        ("Calgary, Alberta, Canada", ("CA", "Alberta", "Calgary")),
        ("Toronto / Vancouver", None),
        ("Remote - Canada", None),
        ("Calgary, AB, US", None),
    ],
)
def test_location_normalization_does_not_guess(raw, expected):
    assert structured_location(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Intern", "INTERNSHIP"),
        ("Co-op", "CO_OP"),
        ("Full Time", "FULL_TIME"),
        ("New Grad", "NEW_GRAD"),
        ("Unknown", "UNSPECIFIED"),
    ],
)
def test_employment_variants(raw, expected):
    assert _employment_type(raw) == expected


def test_company_suffix_and_unknown_work_mode():
    assert normalize_company_identity("Nvidia Corp.") == "Nvidia"
    assert normalize_company_identity("NVIDIA Canada") == "NVIDIA Canada"
    assert _work_mode("maybe remote") == "UNSPECIFIED"


def test_distinct_requisitions_stay_separate_and_direct_copy_merges(isolated_database):
    seed_catalog(isolated_database)
    one = ingest(record(external_id="one", application_url="https://jobs.lever.co/acme/req-one"))
    two = ingest(record(external_id="two", application_url="https://jobs.lever.co/acme/req-two"))
    assert one != two
    direct = ingest(
        record(
            adapter_key="fixture.direct",
            external_id="direct",
            application_url="https://jobs.lever.co/acme/req-one",
        ),
        "OFFICIAL_ATS",
    )
    assert direct == one


def test_changes_field_provenance_locations_and_quality(isolated_database):
    seed_catalog(isolated_database)
    item = record(locations=("Calgary, AB", "Toronto, ON"))
    job_id = ingest(item)
    changed = item.model_copy(update={"description": "New actual responsibilities"})
    ingest(changed)
    ingest(changed)
    assert isolated_database.scalar(select(func.count()).select_from(JobChangeEvent)) == 1
    with UnitOfWork() as uow:
        job = uow.session.get(NormalizedJob, job_id)
        assert set(job.field_provenance) >= {
            "title",
            "description",
            "application_url",
            "requirements_and_locations",
        }
        assert (
            len(
                uow.session.scalars(
                    select(JobLocation).where(
                        JobLocation.job_id == job_id, JobLocation.location_id.is_not(None)
                    )
                ).all()
            )
            == 2
        )
        assert quality_report(uow.session)["observation_authority"] == {"TRUSTED_STRUCTURED": 1}


def test_collector_ingestion_enqueues_only_when_enabled(isolated_database, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_SOURCE_DISCOVERY_ENABLED", True)
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=payload("recruitee")))
    ) as client:
        adapter = create_live_adapter(source("recruitee"), client=client)
        result = LiveJobIngestionService.ingest_adapter(adapter, SourceAdapterRegistry([adapter]))
    assert result.ingested == 1
    assert result.content_hash
    assert isolated_database.scalar(select(func.count()).select_from(SourceDiscoveryWork)) == 2


def test_application_suffix_and_tracking_identity():
    from backend.app.services.canonical_jobs import canonical_url_fingerprint as fp

    assert fp("https://jobs.lever.co/acme/req/apply?utm_source=board") == fp(
        "https://jobs.lever.co/acme/req"
    )
    assert fp("https://acme.recruitee.com/o/swe/c/new") == fp("https://acme.recruitee.com/o/swe")
    assert fp("https://jobs.lever.co/acme/req2") != fp("https://jobs.lever.co/acme/req")


@pytest.mark.parametrize(
    "title,expected",
    [
        ("SWE Intern", ("Software Engineer", "INTERNSHIP", "STUDENT")),
        ("Software Engineer New Grad", ("Software Engineer", "NEW_GRAD", "ENTRY")),
        ("Intern Program Manager", (None, "UNSPECIFIED", "UNSPECIFIED")),
        ("Open position", (None, "UNSPECIFIED", "UNSPECIFIED")),
    ],
)
def test_title_evidence(title, expected):
    from backend.app.ingestion.normalization import title_facts

    assert title_facts(title) == expected


def test_jsonld_multiple_jobs_without_distinct_urls_are_rejected():
    rows = [
        {"@type": "JobPosting", "title": title, "hiringOrganization": {"name": "Acme"}}
        for title in ["Engineer", "Designer"]
    ]
    body = '<script type="application/ld+json">' + json.dumps(rows) + "</script>"
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=body))
    ) as client:
        result = create_live_adapter(source("jsonld"), client=client).fetch_with_metadata()
    assert result.records == () and result.skipped_records == 2
    from backend.app.services.live_collection import LiveCollectionService
    from backend.app.services.live_job_ingestion import LiveSourceIngestionResult

    summary = LiveSourceIngestionResult(
        source_key="test",
        family="jsonld",
        fetched=result.fetched_records,
        parsed=len(result.records),
        ingested=len(result.records),
        malformed=result.skipped_records,
        rejected=0,
        filtered=0,
        complete_listing=result.complete_listing,
    )
    assert not LiveCollectionService._safe_for_lifecycle_reconciliation(summary)


def test_bad_recruitee_url_does_not_drop_good_record():
    data = json.loads(payload("recruitee"))
    data["offers"].append(
        dict(data["offers"][0], id=99, careers_url="https://user:password@example.com/job")
    )
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    ) as client:
        result = create_live_adapter(source("recruitee"), client=client).fetch_with_metadata()
    assert len(result.records) == 1 and result.skipped_records == 1
    from backend.app.services.live_collection import LiveCollectionService
    from backend.app.services.live_job_ingestion import LiveSourceIngestionResult

    summary = LiveSourceIngestionResult(
        source_key="test",
        family="jsonld",
        fetched=result.fetched_records,
        parsed=len(result.records),
        ingested=len(result.records),
        malformed=result.skipped_records,
        rejected=0,
        filtered=0,
        complete_listing=result.complete_listing,
    )
    assert not LiveCollectionService._safe_for_lifecycle_reconciliation(summary)


def test_semantic_fetch_hash_ignores_vendor_json_formatting(isolated_database):
    values = []
    for body in [
        payload("recruitee"),
        json.dumps(json.loads(payload("recruitee")), indent=4, sort_keys=True),
    ]:
        with httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, text=body))
        ) as client:
            adapter = create_live_adapter(source("recruitee"), client=client)
            values.append(
                LiveJobIngestionService.ingest_adapter(
                    adapter, SourceAdapterRegistry([adapter])
                ).content_hash
            )
    assert values[0] == values[1]


def test_replay_retention_and_over_budget_do_not_affect_ingestion(isolated_database):
    for index in range(12):
        data = json.loads(payload("recruitee"))
        data["offers"][0]["description"] = f"Version {index}"
        with httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data))
        ) as client:
            adapter = create_live_adapter(source("recruitee"), client=client)
            result = adapter.fetch_with_metadata()
            preserve_fetch(adapter)
    assert isolated_database.scalar(select(func.count()).select_from(SourceFetchEvidence)) == 10
    adapter.evidence_truncated = True
    assert preserve_fetch(adapter) is None
    assert (
        LiveJobIngestionService.ingest_adapter(
            adapter, SourceAdapterRegistry([adapter]), fetch_result=result
        ).ingested
        == 1
    )


def test_discovery_retries_and_expires_crashed_last_attempt(isolated_database):
    enqueue_urls(
        [
            record(
                application_url="https://employer.example/job",
                source_url="https://employer.example/job",
            )
        ],
        "parent",
    )
    clock = datetime.now(timezone.utc) + timedelta(minutes=1)

    def fetch(url, **kw):
        return httpx.Response(503, request=httpx.Request("GET", url))

    assert process_discovery(fetch=fetch, now=lambda: clock) == ["PENDING"]
    clock += timedelta(hours=1)
    assert process_discovery(fetch=fetch, now=lambda: clock) == ["PENDING"]
    with UnitOfWork() as uow:
        row = uow.session.scalar(select(SourceDiscoveryWork))
        row.attempts = 3
        row.due_at = clock
        uow.commit()
    assert process_discovery(fetch=fetch, now=lambda: clock) == []
    with UnitOfWork() as uow:
        assert uow.session.scalar(select(SourceDiscoveryWork)).state == "FAILED"


@pytest.mark.parametrize("mode", ["redirect_loop", "compressed", "oversized", "slow"])
def test_public_fetch_resource_limits(monkeypatch, mode):
    import backend.app.ingestion.public_http as module

    class Response:
        status = 302 if mode == "redirect_loop" else 200

        def getheader(self, key, default=None):
            return {
                "Location": "http://example.com/again",
                "Content-Encoding": "gzip" if mode == "compressed" else "identity",
                "Content-Length": str(module.MAX_BYTES + 1) if mode == "oversized" else None,
            }.get(key, default)

        def read1(self, size):
            return b"a"

    class Connection:
        def __init__(self, *a, **kw):
            pass

        def request(self, *a, **kw):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            pass

    ticks = iter([0, 0, 31])
    monkeypatch.setattr(module, "public_addresses", lambda *a: ["93.184.216.34"])
    monkeypatch.setattr(module.http.client, "HTTPConnection", Connection)
    monkeypatch.setattr(
        module.socket,
        "create_connection",
        lambda *a, **kw: SimpleNamespace(settimeout=lambda *a: None),
    )
    if mode == "slow":
        monkeypatch.setattr(module.time, "monotonic", lambda: next(ticks))
    with pytest.raises((ValueError, httpx.ReadTimeout)):
        public_get("http://example.com/job")


def test_concurrent_registry_and_source_state_creation(database_engine):
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4

    from sqlalchemy import delete
    from sqlalchemy.orm import sessionmaker

    from backend.app.repositories.live_collection import LiveSourceStateRepository

    config = detect_source(f"https://jobs.lever.co/test{uuid4().hex[:16]}/req", "Concurrency Test")
    factory = sessionmaker(bind=database_engine)

    def uow_factory():
        return UnitOfWork(session_factory=factory)

    def run():
        configs = effective_sources((config,), uow_factory, include_discovered=False)
        with uow_factory() as uow:
            LiveSourceStateRepository(uow.session).synchronize_configurations(
                configs, {config.key: 900}, datetime.now(timezone.utc)
            )
            uow.commit()
        return len(configs)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            assert list(executor.map(lambda _: run(), range(2))) == [1, 1]
        with factory() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(SourceRegistry)
                    .where(SourceRegistry.source_key == config.key)
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(LiveSourceState)
                    .where(LiveSourceState.source_key == config.key)
                )
                == 1
            )
    finally:
        with database_engine.begin() as connection:
            connection.execute(
                delete(LiveSourceState).where(LiveSourceState.source_key == config.key)
            )
            connection.execute(
                delete(SourceRegistry).where(SourceRegistry.source_key == config.key)
            )


def test_dns_timeout_is_bounded(monkeypatch):
    import threading

    event = threading.Event()

    def resolver(*args, **kwargs):
        event.wait(1)
        return [(0, 0, 0, "", ("93.184.216.34", 443))]

    monkeypatch.setattr("socket.getaddrinfo", resolver)
    try:
        with pytest.raises(httpx.ConnectTimeout):
            public_addresses("example.com", 443, timeout=0.01)
    finally:
        event.set()
