"""Offline regression for bounded Greenhouse list/detail fallback."""

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.ingestion.live import LiveSourceFetchError, create_live_adapter
from backend.app.ingestion.public_http import MAX_BYTES
from backend.app.models.intelligence import SourceFetchEvidence
from backend.app.models.job import (
    JobSourceObservation,
    JobSourceRecord,
    LiveSourceState,
    NormalizedJob,
)
from backend.app.services.source_intelligence import replay_fetch
from backend.tests.test_live_collection import (
    Clock,
    collector,
    greenhouse_job,
    install_mock_adapters,
    source_config,
)


def oversized():
    # Exercise production streaming-client rejection without allocating a giant fixture.
    return ValueError("Response too large")


def listing(*ids):
    return httpx.Response(200, json={"jobs": [{"id": value} for value in ids]})


def detail(value):
    return httpx.Response(200, json=greenhouse_job(
        id=value, absolute_url=f"https://boards.greenhouse.io/acme/jobs/{value}",
        title=f"Platform Engineer {value}",
    ))


def test_small_board_keeps_one_request():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"jobs": [greenhouse_job()]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = create_live_adapter(source_config(), client=client).fetch_with_metadata()
    assert len(calls) == 1 and calls[0].url.params["content"] == "true"
    assert len(result.records) == 1 and result.complete_listing
    assert result.continuation is None


def test_cap_and_bounded_details():
    assert MAX_BYTES == 5 * 1024 * 1024
    responses = [oversized(), listing(1, 2, 2, 3), detail(1), detail(2)]
    calls = []
    def handler(request):
        calls.append(request)
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result
    config = source_config().model_copy(update={"max_postings": 2})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = create_live_adapter(config, client=client).fetch_with_metadata()
    assert [r.external_id for r in result.records] == ["1", "2"]
    assert result.continuation == "gh:acme:2" and not result.complete_listing
    assert len(calls) == 4 and not calls[1].url.query


@pytest.mark.parametrize("failure", [
    httpx.Response(429, headers={"Retry-After": "120"}),
    httpx.Response(503),
    httpx.ReadTimeout("timeout"),
    ValueError("Response too large"),
])
def test_partial_commits_resume_and_no_absence(monkeypatch, isolated_database, failure):
    config = source_config().model_copy(update={"max_postings": 2})
    # Initial small-board jobs remain live through repeated partial/failed traversals.
    initial = httpx.Response(200, json={"jobs": [greenhouse_job(
        id=99, absolute_url="https://boards.greenhouse.io/acme/jobs/99",
    )]})
    requests, clients = install_mock_adapters(monkeypatch, {config.key: [
        initial, oversized(), listing(1, 2, 3), detail(1), failure,
        listing(1, 2, 3), detail(2), detail(3),
        listing(1, 2, 3), detail(1), detail(2),
    ]})
    clock = Clock()
    service = collector([config], clock)
    assert service.run_cycle(force=True).failed == 0
    failed = service.run_cycle(force=True).outcomes[0]
    assert not failed.succeeded and failed.result.ingested == 1
    with Session(isolated_database) as session:
        state = session.scalar(select(LiveSourceState))
        assert state.retrieval_cursor == "gh:acme:1"
        assert state.consecutive_failures == 1
        if isinstance(failure, httpx.Response) and failure.status_code == 429:
            assert state.health == "RATE_LIMITED"
            assert (state.next_poll_at - clock()).total_seconds() >= 120
    # Construct a new collector to demonstrate durable continuation after restart.
    assert collector([config], clock).run_cycle(force=True).failed == 0
    assert collector([config], clock).run_cycle(force=True).failed == 0
    with Session(isolated_database) as session:
        assert session.scalar(select(func.count()).select_from(JobSourceRecord)) == 4
        assert session.scalar(select(func.count()).select_from(NormalizedJob)) == 4
        unseen = session.scalar(select(JobSourceObservation).join(JobSourceRecord, JobSourceRecord.id == JobSourceObservation.job_source_record_id).where(JobSourceRecord.external_id == "99"))
        assert unseen.consecutive_absent_successes == 0
        assert not unseen.explicitly_closed and unseen.closed_at is None
        evidence = session.scalars(select(SourceFetchEvidence).where(
            SourceFetchEvidence.parser_version == "greenhouse-detail-v1"
        )).all()
        assert evidence and len(evidence) <= 10
        assert all(len(row.pages) == 1 for row in evidence)
        assert replay_fetch(config.key, evidence[0].content_hash).records
    assert sum(bool(req.url.query) for req in requests[config.key]) == 2
    for client in clients:
        client.close()


def test_empty_list_is_authoritative_but_exhausted_cursor_is_not():
    for ids, complete in [((), True), ((1,), False)]:
        with httpx.Client(transport=httpx.MockTransport(lambda _: listing(*ids))) as client:
            adapter = create_live_adapter(source_config(), client=client)
            result = list(adapter.fetch_batches(continuation="gh:acme:100"))[0]
        assert result.records == () and result.complete_listing is complete
        assert result.continuation == "gh:acme:0"


@pytest.mark.parametrize("response", [oversized(), httpx.Response(503)])
def test_lightweight_list_itself_must_be_safe(response):
    def handler(_):
        if isinstance(response, Exception):
            raise response
        return response
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = create_live_adapter(source_config(), client=client)
        with pytest.raises(LiveSourceFetchError):
            list(adapter.fetch_batches(continuation="gh:acme:0"))


def test_detail_identity_mismatch_fails_safely():
    responses = [listing(1), detail(2)]
    with httpx.Client(transport=httpx.MockTransport(lambda _: responses.pop(0))) as client:
        adapter = create_live_adapter(source_config(), client=client)
        with pytest.raises(LiveSourceFetchError, match="ID mismatch"):
            list(adapter.fetch_batches(continuation="gh:acme:0"))


def test_fifty_detail_cap_and_per_detail_evidence():
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/jobs"):
            return listing(*range(1, 102))
        return detail(int(request.url.path.rsplit("/", 1)[1]))
    config = source_config().model_copy(update={"max_postings": 250})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = create_live_adapter(config, client=client)
        batches = []
        for batch in adapter.fetch_batches(continuation="gh:acme:0"):
            batches.append(batch)
            assert len(adapter.evidence_pages) == 1
    assert len(calls) == 51 and len(batches) == 50
    assert batches[-1].continuation == "gh:acme:50"
    assert not any(batch.complete_listing for batch in batches)


def test_time_budget_returns_progress(monkeypatch):
    import backend.app.ingestion.live as live

    ticks = iter([0, 61])
    monkeypatch.setattr(live, "monotonic", lambda: next(ticks))
    responses = [listing(1, 2), detail(1)]
    with httpx.Client(transport=httpx.MockTransport(lambda _: responses.pop(0))) as client:
        batches = list(create_live_adapter(source_config(), client=client).fetch_batches(
            continuation="gh:acme:0"
        ))
    assert len(batches) == 1 and batches[0].continuation == "gh:acme:1"


def test_oversized_buffered_response_uses_same_fallback():
    responses = [httpx.Response(200, content=b"x" * (MAX_BYTES + 1)), listing()]
    with httpx.Client(transport=httpx.MockTransport(lambda _: responses.pop(0))) as client:
        result = create_live_adapter(source_config(), client=client).fetch_with_metadata()
    assert result.complete_listing and result.records == ()


def test_invalid_cursor_does_not_make_request():
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("Unexpected HTTP"))) as client:
        with pytest.raises(LiveSourceFetchError, match="continuation"):
            list(create_live_adapter(source_config(), client=client).fetch_batches(
                continuation="gh:acme:bad"
            ))


def test_calibration_reports_fallback_within_sample_budget():
    from backend.app.services.coverage_calibration import DEFAULT_FIXTURE, _probe

    requests = []
    def fetch(url, **_):
        requests.append(url)
        if "content=true" in url:
            raise ValueError("Response too large")
        if url.endswith("/jobs"):
            return listing(*range(1, 8))
        return detail(int(url.rsplit("/", 1)[1]))
    result, records = _probe(
        {"company": "Acme", "url": "https://boards.greenhouse.io/acme", "provider": "greenhouse"},
        live=True, base=DEFAULT_FIXTURE.parent, timeout=10, fetch=fetch,
    )
    assert result["status"] == "SUCCESS"
    assert result["retrieval_strategy"] == "list-detail"
    assert result["continuation"] == "gh:acme:5"
    assert not result["complete_listing"]
    assert len(requests) == 7 and len(records) == 5


def test_large_board_empty_observation_retains_existing_closure_threshold(monkeypatch, isolated_database):
    config = source_config()
    responses = [
        httpx.Response(200, json={"jobs": [greenhouse_job()]}),
        oversized(), listing(), listing(),
    ]
    _, clients = install_mock_adapters(monkeypatch, {config.key: responses})
    service = collector([config], Clock())
    service.run_cycle(force=True)
    service.run_cycle(force=True)
    with Session(isolated_database) as session:
        observation = session.scalar(select(JobSourceObservation))
        assert observation.consecutive_absent_successes == 1
        assert observation.closed_at is None
    service.run_cycle(force=True)
    with Session(isolated_database) as session:
        observation = session.scalar(select(JobSourceObservation))
        assert observation.consecutive_absent_successes == 2
        assert session.get(NormalizedJob, observation.canonical_job_id).closed_at is not None
    for client in clients:
        client.close()
