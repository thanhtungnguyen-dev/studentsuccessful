"""Focused deterministic coverage for Phase 19 collection and source health."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import backend.app.services.live_collection as collection_module
from backend.app.ingestion.live import (
    LiveJobSourceConfig,
    LiveSourceFetchError,
    create_live_adapter,
)
from backend.app.main import app
from backend.app.models.application import Application
from backend.app.models.job import (
    JobSourceRecord,
    LiveSourceHealth,
    LiveSourceState,
    NormalizedJob,
    RawJobSnapshot,
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
from backend.app.repositories.live_collection import LiveSourceClaim
from backend.app.services.live_collection import (
    LiveCollectionOutcome,
    LiveCollectionService,
    bounded_backoff_seconds,
)
from backend.app.services.live_job_ingestion import LiveSourceIngestionResult

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def set(self, value: datetime) -> None:
        self.value = value


def source_config(
    *,
    key: str = "greenhouse.acme",
    enabled: bool = True,
    poll_interval_seconds: int = 300,
) -> LiveJobSourceConfig:
    return LiveJobSourceConfig.model_validate(
        {
            "key": key,
            "family": "greenhouse",
            "company": "Acme LLC",
            "role": "Unspecified",
            "enabled": enabled,
            "board_token": "acme",
            "max_postings": 10,
            "poll_interval_seconds": poll_interval_seconds,
        }
    )


def greenhouse_job(**changes) -> dict[str, object]:
    value: dict[str, object] = {
        "id": 101,
        "title": "Platform Engineering Intern",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/101",
        "content": "<p>Build <strong>platforms</strong>.</p>",
        "location": {"name": "Toronto, Canada"},
        "first_published": "2026-09-01T09:30:00Z",
        "updated_at": "2026-09-02T09:30:00Z",
    }
    value.update(changes)
    return value


def greenhouse_payload(*jobs: object) -> dict[str, object]:
    return {"jobs": list(jobs)}


def install_mock_adapters(monkeypatch, responses: dict[str, list[object]]):
    """Patch only the collector's adapter construction; all provider replies stay local."""

    pending = {key: list(values) for key, values in responses.items()}
    requests: dict[str, list[httpx.Request]] = {key: [] for key in responses}
    clients: list[httpx.Client] = []

    def factory(config: LiveJobSourceConfig, *, timeout_seconds: float):
        def handler(request: httpx.Request) -> httpx.Response:
            requests[config.key].append(request)
            try:
                result = pending[config.key].pop(0)
            except IndexError as exc:
                raise AssertionError(f"unexpected request for {config.key}") from exc
            if isinstance(result, Exception):
                raise result
            assert isinstance(result, httpx.Response)
            return result

        client = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(client)
        return create_live_adapter(config, timeout_seconds=timeout_seconds, client=client)

    monkeypatch.setattr(collection_module, "create_live_adapter", factory)
    return requests, clients


def collector(configs, clock: Clock, **changes) -> LiveCollectionService:
    return LiveCollectionService(
        configs,
        default_timeout_seconds=10,
        max_concurrency=changes.pop("max_concurrency", 1),
        max_backoff_seconds=changes.pop("max_backoff_seconds", 300),
        now=clock,
        jitter=changes.pop("jitter", lambda _key, _base, _attempt: 0),
        **changes,
    )


def state(connection, key: str) -> LiveSourceState:
    session = Session(bind=connection)
    try:
        persisted = session.scalar(select(LiveSourceState).where(LiveSourceState.source_key == key))
        assert persisted is not None
        return persisted
    finally:
        session.close()


def success_result(key: str, family: str = "greenhouse") -> LiveSourceIngestionResult:
    return LiveSourceIngestionResult(
        source_key=key,
        family=family,
        fetched=1,
        parsed=1,
        ingested=1,
        malformed=0,
        rejected=0,
        filtered=0,
        http_status=200,
    )


def test_enabled_source_is_scheduled_and_success_updates_durable_health(
    isolated_database, monkeypatch
):
    config = source_config()
    clock = Clock()
    requests, clients = install_mock_adapters(
        monkeypatch,
        {config.key: [httpx.Response(200, json=greenhouse_payload(greenhouse_job()))]},
    )
    try:
        cycle = collector((config,), clock).run_cycle(force=True)
    finally:
        for client in clients:
            client.close()

    assert cycle.attempted == 1 and cycle.failed == 0
    persisted = state(isolated_database, config.key)
    assert persisted.health == LiveSourceHealth.HEALTHY
    assert persisted.last_attempt_at == NOW
    assert persisted.last_success_at == NOW
    assert persisted.last_jobs_seen == persisted.last_jobs_ingested == 1
    assert persisted.next_poll_at == NOW + timedelta(seconds=300)
    assert len(requests[config.key]) == 1


def test_disabled_source_is_persisted_as_disabled_and_not_fetched(isolated_database, monkeypatch):
    config = source_config(enabled=False)
    clock = Clock()
    requests, clients = install_mock_adapters(monkeypatch, {config.key: []})
    try:
        cycle = collector((config,), clock).run_cycle(force=True)
    finally:
        for client in clients:
            client.close()

    assert cycle.outcomes == ()
    persisted = state(isolated_database, config.key)
    assert (persisted.enabled, persisted.health, persisted.next_poll_at) == (
        False,
        LiveSourceHealth.DISABLED,
        None,
    )
    assert requests[config.key] == []


def test_timeout_does_not_block_another_source_and_failure_is_isolated(
    isolated_database, monkeypatch
):
    failed = source_config(key="greenhouse.failed")
    healthy = source_config(key="greenhouse.healthy").model_copy(update={"board_token": "healthy"})
    clock = Clock()
    _, clients = install_mock_adapters(
        monkeypatch,
        {
            failed.key: [httpx.ReadTimeout("timed out")],
            healthy.key: [httpx.Response(200, json=greenhouse_payload(greenhouse_job(id=202)))],
        },
    )
    try:
        cycle = collector((failed, healthy), clock).run_cycle(force=True)
    finally:
        for client in clients:
            client.close()

    assert [(outcome.source_key, outcome.succeeded) for outcome in cycle.outcomes] == [
        (failed.key, False),
        (healthy.key, True),
    ]
    assert state(isolated_database, failed.key).last_error_category == "TIMEOUT"
    assert state(isolated_database, healthy.key).health == LiveSourceHealth.HEALTHY
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 1


def test_rate_limit_marks_health_and_respects_retry_after(isolated_database, monkeypatch):
    config = source_config()
    clock = Clock()
    _, clients = install_mock_adapters(
        monkeypatch,
        {config.key: [httpx.Response(429, json={"error": "slow down"}, headers={"Retry-After": "180"})]},
    )
    try:
        cycle = collector((config,), clock).run_cycle(force=True)
    finally:
        for client in clients:
            client.close()

    assert cycle.failed == 1
    persisted = state(isolated_database, config.key)
    assert (persisted.health, persisted.last_error_category, persisted.last_http_status) == (
        LiveSourceHealth.RATE_LIMITED,
        "RATE_LIMITED",
        429,
    )
    assert persisted.next_poll_at == NOW + timedelta(seconds=180)


def test_repeated_failures_back_off_with_a_bounded_deterministic_schedule_and_recover(
    isolated_database, monkeypatch
):
    config = source_config()
    clock = Clock()
    _, clients = install_mock_adapters(
        monkeypatch,
        {
            config.key: [
                httpx.Response(503, json={"error": "temporary"}),
                httpx.Response(503, json={"error": "temporary"}),
                httpx.Response(200, json=greenhouse_payload(greenhouse_job())),
            ]
        },
    )
    service = collector((config,), clock)
    try:
        service.run_cycle(force=True)
        first = state(isolated_database, config.key)
        assert (first.consecutive_failures, first.next_poll_at) == (1, NOW + timedelta(seconds=60))

        clock.set(first.next_poll_at)
        service.run_cycle()
        second = state(isolated_database, config.key)
        assert (second.consecutive_failures, second.next_poll_at) == (
            2,
            clock.value + timedelta(seconds=120),
        )

        clock.set(second.next_poll_at)
        service.run_cycle()
    finally:
        for client in clients:
            client.close()

    recovered = state(isolated_database, config.key)
    assert (recovered.health, recovered.consecutive_failures, recovered.last_error_category) == (
        LiveSourceHealth.HEALTHY,
        0,
        None,
    )
    assert bounded_backoff_seconds(config.key, 9, max_backoff_seconds=300, jitter=lambda *_: 0) == 300


def test_conditional_fetch_uses_provider_validator_and_304_keeps_source_healthy(
    isolated_database, monkeypatch
):
    config = source_config()
    clock = Clock()
    requests, clients = install_mock_adapters(
        monkeypatch,
        {
            config.key: [
                httpx.Response(
                    200,
                    json=greenhouse_payload(greenhouse_job()),
                    headers={"ETag": '"revision-1"'},
                ),
                httpx.Response(304, headers={"ETag": '"revision-1"'}),
            ]
        },
    )
    service = collector((config,), clock)
    try:
        service.run_cycle(force=True)
        clock.set(NOW + timedelta(seconds=300))
        cycle = service.run_cycle(force=True)
    finally:
        for client in clients:
            client.close()

    assert cycle.outcomes[0].result is not None and cycle.outcomes[0].result.not_modified
    assert requests[config.key][1].headers["if-none-match"] == '"revision-1"'
    persisted = state(isolated_database, config.key)
    assert (persisted.health, persisted.last_jobs_seen, persisted.etag) == (
        LiveSourceHealth.HEALTHY,
        1,
        '"revision-1"',
    )


def test_suspicious_empty_success_becomes_degraded_without_closing_existing_jobs(
    isolated_database, monkeypatch
):
    config = source_config()
    clock = Clock()
    _, clients = install_mock_adapters(
        monkeypatch,
        {
            config.key: [
                httpx.Response(200, json=greenhouse_payload(greenhouse_job())),
                httpx.Response(200, json=greenhouse_payload()),
            ]
        },
    )
    service = collector((config,), clock)
    try:
        service.run_cycle(force=True)
        clock.set(NOW + timedelta(seconds=300))
        service.run_cycle(force=True)
    finally:
        for client in clients:
            client.close()

    persisted = state(isolated_database, config.key)
    assert (persisted.health, persisted.consecutive_empty_successes, persisted.last_jobs_seen) == (
        LiveSourceHealth.DEGRADED,
        1,
        0,
    )
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 1


def test_source_stale_detection_is_conservative_and_recovers_on_a_success(
    isolated_database, monkeypatch
):
    config = source_config()
    clock = Clock()
    _, clients = install_mock_adapters(
        monkeypatch,
        {
            config.key: [
                httpx.Response(200, json=greenhouse_payload(greenhouse_job())),
                httpx.Response(200, json=greenhouse_payload(greenhouse_job())),
            ]
        },
    )
    service = collector((config,), clock)
    try:
        service.run_cycle(force=True)
        clock.set(NOW + timedelta(seconds=601))
        service.synchronize()
        assert state(isolated_database, config.key).health == LiveSourceHealth.STALE
        service.run_cycle(force=True)
    finally:
        for client in clients:
            client.close()

    assert state(isolated_database, config.key).health == LiveSourceHealth.HEALTHY


def test_repeated_polls_after_a_collector_restart_are_idempotent_and_jobs_are_visible(
    isolated_database, monkeypatch
):
    config = source_config()
    clock = Clock()
    _, clients = install_mock_adapters(
        monkeypatch,
        {
            config.key: [
                httpx.Response(200, json=greenhouse_payload(greenhouse_job())),
                httpx.Response(200, json=greenhouse_payload(greenhouse_job())),
            ]
        },
    )
    try:
        collector((config,), clock).run_cycle(force=True)
        clock.set(NOW + timedelta(seconds=300))
        collector((config,), clock).run_cycle(force=True)
    finally:
        for client in clients:
            client.close()

    assert isolated_database.scalar(select(func.count()).select_from(JobSourceRecord)) == 1
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 1
    assert isolated_database.scalar(select(func.count()).select_from(RawJobSnapshot)) == 1
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"collector-{uuid4().hex}@example.com", "password": "Password123!"},
    )
    assert response.status_code == 201
    listing = client.get("/api/v1/jobs?keyword=Platform")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["title"] == "Platform Engineering Intern"


def test_failed_poll_never_deletes_a_previously_valid_job(isolated_database, monkeypatch):
    config = source_config()
    clock = Clock()
    _, clients = install_mock_adapters(
        monkeypatch,
        {
            config.key: [
                httpx.Response(200, json=greenhouse_payload(greenhouse_job())),
                httpx.Response(503, json={"error": "temporary"}),
            ]
        },
    )
    service = collector((config,), clock)
    try:
        service.run_cycle(force=True)
        clock.set(NOW + timedelta(seconds=300))
        service.run_cycle(force=True)
    finally:
        for client in clients:
            client.close()

    assert state(isolated_database, config.key).health == LiveSourceHealth.FAILING
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 1


def test_collection_never_mutates_candidate_owned_data(isolated_database, monkeypatch):
    config = source_config()
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
    before = {table.name: isolated_database.scalar(select(func.count()).select_from(table)) for table in tables}
    _, clients = install_mock_adapters(
        monkeypatch,
        {config.key: [httpx.Response(200, json=greenhouse_payload(greenhouse_job()))]},
    )
    try:
        collector((config,), Clock()).run_cycle(force=True)
    finally:
        for client in clients:
            client.close()
    after = {table.name: isolated_database.scalar(select(func.count()).select_from(table)) for table in tables}
    assert after == before


def test_bounded_concurrency_limits_independent_source_workers(monkeypatch):
    configs = tuple(source_config(key=f"greenhouse.concurrent-{index}") for index in range(3))
    claims = tuple(
        LiveSourceClaim(
            config=config,
            token=uuid4(),
            etag=None,
            last_modified=None,
            normal_poll_interval_seconds=300,
        )
        for config in configs
    )
    service = collector(configs, Clock(), max_concurrency=2)
    entered = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    active = 0
    maximum = 0
    recorded: list[LiveCollectionOutcome] = []

    def collect_claim(claim, registry, stop_event=None):
        nonlocal active, maximum
        del registry
        with lock:
            active += 1
            maximum = max(maximum, active)
            if active == 2:
                entered.set()
        release.wait(timeout=2)
        with lock:
            active -= 1
        return LiveCollectionOutcome(claim.config.key, claim.config.family, success_result(claim.config.key))

    monkeypatch.setattr(service, "synchronize", lambda now=None: None)
    monkeypatch.setattr(service, "_claim_due", lambda now, force, limit=None: claims)
    monkeypatch.setattr(service, "_collect_claim", collect_claim)
    monkeypatch.setattr(
        service,
        "_record_outcome",
        lambda claim, outcome, completed: recorded.append(outcome),
    )

    holder: list[object] = []
    worker = threading.Thread(target=lambda: holder.append(service.run_cycle(force=True)))
    worker.start()
    assert entered.wait(timeout=2)
    with lock:
        assert maximum == active == 2
    release.set()
    worker.join(timeout=3)

    assert not worker.is_alive()
    assert len(recorded) == 3
    assert len(holder) == 1


def test_slow_timeout_worker_does_not_prevent_a_healthy_worker(monkeypatch):
    slow = source_config(key="greenhouse.slow")
    healthy = source_config(key="greenhouse.fast")
    claims = tuple(
        LiveSourceClaim(
            config=config,
            token=uuid4(),
            etag=None,
            last_modified=None,
            normal_poll_interval_seconds=300,
        )
        for config in (slow, healthy)
    )
    service = collector((slow, healthy), Clock(), max_concurrency=2)
    slow_started = threading.Event()
    healthy_started = threading.Event()
    release_slow = threading.Event()
    recorded: list[LiveCollectionOutcome] = []

    def collect_claim(claim, registry, stop_event=None):
        del registry
        if claim.config.key == slow.key:
            slow_started.set()
            release_slow.wait(timeout=2)
            raise LiveSourceFetchError("timed out", category="TIMEOUT")
        healthy_started.set()
        return LiveCollectionOutcome(claim.config.key, claim.config.family, success_result(claim.config.key))

    monkeypatch.setattr(service, "synchronize", lambda now=None: None)
    monkeypatch.setattr(service, "_claim_due", lambda now, force, limit=None: claims)
    monkeypatch.setattr(service, "_collect_claim", collect_claim)
    monkeypatch.setattr(
        service,
        "_record_outcome",
        lambda claim, outcome, completed: recorded.append(outcome),
    )

    holder: list[object] = []
    worker = threading.Thread(target=lambda: holder.append(service.run_cycle(force=True)))
    worker.start()
    assert slow_started.wait(timeout=2)
    assert healthy_started.wait(timeout=2)
    release_slow.set()
    worker.join(timeout=3)

    assert not worker.is_alive()
    assert {(outcome.source_key, outcome.succeeded, outcome.error_category) for outcome in recorded} == {
        (slow.key, False, "TIMEOUT"),
        (healthy.key, True, None),
    }
    assert len(holder) == 1
