"""Deterministic worker-loop, liveness and crash recovery checks."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.app.commands.collect_live import _run_forever
from backend.app.models.job import LiveSourceState
from backend.app.repositories.live_collection import LiveSourceStateRepository
from backend.app.services.live_collection import LiveCollectionCycle
from backend.app.services.worker_runtime import WorkerRuntime, operational_status, worker_health
from backend.tests.test_live_collection import (
    Clock,
    collector,
    install_mock_adapters,
    source_config,
)


class Stop:
    def __init__(self, waits=1):
        self.stopped = False
        self.delays = []
        self.waits = waits

    def is_set(self):
        return self.stopped

    def set(self):
        self.stopped = True

    def wait(self, delay):
        self.delays.append(delay)
        if len(self.delays) >= self.waits:
            self.set()


def idle_service():
    return SimpleNamespace(
        run_cycle=Mock(return_value=LiveCollectionCycle(())),
        seconds_until_next_poll=Mock(return_value=60),
    )


def runtime_mock():
    return SimpleNamespace(
        owns_lease=False, lease_seconds=120,
        claim=Mock(return_value=True), heartbeat=Mock(return_value=True), release=Mock(),
    )


def test_startup_idle_heartbeat_stop_and_identity(isolated_database):
    clock = Clock()
    runtime = WorkerRuntime("collector", now=clock)
    other = WorkerRuntime("collector", now=clock)
    stop = Stop()
    service = idle_service()
    def cycle(**kwargs):
        kwargs["on_tick"]()
        with Session(isolated_database) as session:
            state = operational_status(session, now=clock())["workers"][0]
            assert state["runtime_id"] == str(runtime.token)
            assert state["started_at"] == clock()
            assert state["heartbeat_age_seconds"] == 0
            assert state["status"] == "healthy"
        return LiveCollectionCycle(())
    service.run_cycle.side_effect = cycle
    assert _run_forever(service, stop_event=stop, runtime=runtime) == 0
    assert runtime.token != other.token
    assert stop.delays == [20]
    with Session(isolated_database) as session:
        assert worker_health("collector", session=session, now=clock()).status == "stopped"


def test_stale_heartbeat_without_cleanup_then_reclaim(isolated_database):
    clock = Clock()
    first = WorkerRuntime("collector", now=clock, lease_seconds=60)
    second = WorkerRuntime("collector", now=clock, lease_seconds=60)
    assert first.claim() and not second.claim()
    clock.value += timedelta(seconds=61)
    with Session(isolated_database) as session:
        assert worker_health("collector", session=session, now=clock()).status == "stale"
    assert second.claim()
    assert not first.heartbeat() and not first.release()


@pytest.mark.parametrize("stage", ["claim", "heartbeat", "cycle", "idle"])
def test_database_failures_retry_with_bounded_sleep(stage):
    service, runtime, stop = idle_service(), runtime_mock(), Stop(waits=6)
    error = OperationalError("not logged", {}, Exception("private database error"))
    target = {"claim": runtime.claim, "heartbeat": runtime.heartbeat,
              "cycle": service.run_cycle, "idle": service.seconds_until_next_poll}[stage]
    target.side_effect = error
    assert _run_forever(service, runtime=runtime, stop_event=stop) == 0
    assert stop.delays == [5, 10, 20, 40, 60, 60]
    runtime.release.assert_called_once()


def test_database_recovery_returns_to_normal_idle():
    service, runtime, stop = idle_service(), runtime_mock(), Stop(waits=2)
    runtime.claim.side_effect = [OperationalError("", {}, Exception()), True]
    assert _run_forever(service, runtime=runtime, stop_event=stop) == 0
    assert stop.delays == [5, 20]
    assert service.run_cycle.call_count == 1


def test_stop_prevents_new_claims():
    service, runtime, stop = idle_service(), runtime_mock(), Stop()
    stop.set()
    assert _run_forever(service, runtime=runtime, stop_event=stop) == 0
    runtime.claim.assert_not_called()
    service.run_cycle.assert_not_called()


def test_stop_propagates_during_work():
    service, runtime, stop = idle_service(), runtime_mock(), Stop()
    def cycle(**kwargs):
        stop.set()
        kwargs["on_tick"]()
        assert kwargs["stop_event"].is_set()
        return LiveCollectionCycle(())
    service.run_cycle.side_effect = cycle
    assert _run_forever(service, runtime=runtime, stop_event=stop) == 0
    assert service.run_cycle.call_count == 1


def test_once_runs_real_due_cycle_contract_without_sleep():
    service, runtime, stop = idle_service(), runtime_mock(), Stop()
    assert _run_forever(service, runtime=runtime, stop_event=stop, once=True) == 0
    assert service.run_cycle.call_args.kwargs["force"] is False
    assert stop.delays == []
    runtime.release.assert_called_once()


def test_standby_sleeps_instead_of_spinning():
    service, runtime, stop = idle_service(), runtime_mock(), Stop()
    runtime.claim.return_value = False
    assert _run_forever(service, runtime=runtime, stop_event=stop) == 0
    assert stop.delays == [5]
    service.run_cycle.assert_not_called()


def test_release_failure_is_visible_but_shutdown_exits(monkeypatch):
    runtime = runtime_mock()
    runtime.release.side_effect = OperationalError("", {}, Exception())
    logger = Mock()
    monkeypatch.setattr("backend.app.commands.collect_live.logger", logger)
    assert _run_forever(idle_service(), runtime=runtime, once=True) == 0
    logger.exception.assert_called_once_with("worker_release_failed", extra={"worker": "collector"})


def test_expired_source_lease_recovers_cursor_and_overdue_work(isolated_database):
    config, clock = source_config(), Clock()
    service = collector([config], clock)
    service.synchronize()
    first = service._claim_due(clock(), force=False)[0]
    assert service._claim_due(clock(), force=False) == ()
    with Session(isolated_database) as session:
        row = session.scalar(select(LiveSourceState))
        row.retrieval_cursor = "gh:acme:42"
        session.commit()
    clock.value += timedelta(seconds=151)
    replacement = collector([config], clock)._claim_due(clock(), force=False)[0]
    assert replacement.token != first.token
    assert replacement.retrieval_cursor == "gh:acme:42"
    with Session(isolated_database) as session:
        assert LiveSourceStateRepository(session).claimed_state(config.key, first.token) is None


def test_claim_budget_selects_oldest_due_first(isolated_database):
    configs = [source_config(key="greenhouse.a"), source_config(key="greenhouse.b").model_copy(update={"board_token": "b"})]
    clock = Clock()
    service = collector(configs, clock)
    service.synchronize()
    with Session(isolated_database) as session:
        row = session.scalar(select(LiveSourceState).where(LiveSourceState.source_key == configs[1].key))
        row.next_poll_at = clock() - timedelta(days=1)
        session.commit()
    claims = service._claim_due(clock(), force=False, limit=1)
    assert len(claims) == 1 and claims[0].config.key == configs[1].key


def test_source_failure_does_not_stop_next_due_source(monkeypatch):
    configs = [source_config(key="greenhouse.a"), source_config(key="greenhouse.b").model_copy(update={"board_token": "b"})]
    _, clients = install_mock_adapters(monkeypatch, {
        configs[0].key: [httpx.Response(429)],
        configs[1].key: [httpx.Response(200, json={"jobs": []})],
    })
    result = collector(configs, Clock()).run_cycle()
    assert result.attempted == 2 and result.failed == 1
    for client in clients:
        client.close()


def test_stopped_cycle_never_synchronizes_or_claims():
    stop = Stop()
    stop.set()
    service = collector([], Clock())
    service.synchronize = Mock(side_effect=AssertionError("should not query"))
    assert service.run_cycle(stop_event=stop).attempted == 0


def test_heartbeat_and_source_lease_renew_during_inflight_work(monkeypatch, isolated_database):
    import threading

    import backend.app.services.live_collection as module
    from backend.app.services.live_collection import LiveCollectionOutcome
    from backend.app.services.live_job_ingestion import LiveSourceIngestionResult

    clock, config = Clock(), source_config()
    runtime = WorkerRuntime("collector", now=clock, lease_seconds=60)
    assert runtime.claim()
    service = collector([config], clock)
    release = threading.Event()
    waits = 0
    original_wait = module.wait
    def bounded_work(claim, registry, stop_event=None):
        assert release.wait(3)
        result = LiveSourceIngestionResult(config.key, config.family, 0, 0, 0, 0, 0, 0)
        return LiveCollectionOutcome(config.key, config.family, result)
    def virtual_wait(futures, **kwargs):
        nonlocal waits
        waits += 1
        if waits <= 4:
            clock.value += timedelta(seconds=10)
        if waits == 4:
            release.set()
        return original_wait(futures, timeout=0.01)
    monkeypatch.setattr(service, "_outcome_for_claim", bounded_work)
    monkeypatch.setattr(module, "wait", virtual_wait)
    assert service.run_cycle(on_tick=runtime.heartbeat, stop_event=threading.Event()).attempted == 1
    assert waits >= 4
    with Session(isolated_database) as session:
        assert worker_health("collector", session=session, now=clock()).status == "healthy"
        row = session.scalar(select(LiveSourceState))
        assert row.last_completed_at == clock()
    runtime.release()


def test_interrupted_batch_checkpoint_survives_crash_without_absence(monkeypatch, isolated_database):
    from backend.app.ingestion.adapters import SourceAdapterRegistry
    from backend.app.ingestion.live import create_live_adapter
    from backend.app.models.job import JobSourceObservation, JobSourceRecord
    from backend.tests.test_large_board_retrieval import detail, listing, oversized
    from backend.tests.test_live_collection import greenhouse_job

    config = source_config().model_copy(update={"max_postings": 2})
    clock = Clock()
    _, clients = install_mock_adapters(monkeypatch, {config.key: [
        httpx.Response(200, json={"jobs": [greenhouse_job(id=99)]}),
        listing(1, 2, 3), detail(2), detail(3),
    ]})
    service = collector([config], clock)
    service.run_cycle(force=True)
    claim = service._claim_due(clock(), force=True)[0]
    responses = [oversized(), listing(1, 2, 3), detail(1)]
    def handler(_):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result
    class Interrupt:
        calls = 0
        def is_set(self):
            self.calls += 1
            return self.calls > 1
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = create_live_adapter(config, client=client)
        outcome = service._collect_claim(claim, SourceAdapterRegistry((adapter,)), Interrupt())
    assert outcome.result.ingested == 1 and not outcome.result.complete_listing
    # No cleanup/finally: emulate a killed process and reclaim after lease expiry.
    clock.value += timedelta(seconds=601)
    resumed = collector([config], clock).run_cycle(force=False)
    assert resumed.failed == 0 and resumed.attempted == 1
    with Session(isolated_database) as session:
        rows = session.scalars(select(JobSourceRecord)).all()
        assert {r.external_id for r in rows} == {"99", "1", "2", "3"}
        assert all(r.consecutive_absent_successes == 0 for r in session.scalars(select(JobSourceObservation)))
    for client in clients:
        client.close()


def test_shutdown_before_batch_releases_source_without_failure(isolated_database):
    from backend.app.ingestion.adapters import SourceAdapterRegistry
    from backend.app.ingestion.live import create_live_adapter

    clock, config = Clock(), source_config()
    service = collector([config], clock)
    service.synchronize()
    claim = service._claim_due(clock(), force=False)[0]
    stop = Stop()
    stop.set()
    outcome = service._collect_claim(claim, SourceAdapterRegistry((create_live_adapter(config),)), stop)
    service._record_outcome(claim, outcome, clock())
    with Session(isolated_database) as session:
        state = session.scalar(select(LiveSourceState))
        assert state.lease_token is None and state.lease_expires_at is None
        assert state.total_collection_failures == 0
        assert state.last_error_category is None


def test_simultaneous_first_worker_claims_are_serialized(database_engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import delete
    from sqlalchemy.orm import sessionmaker

    from backend.app.core.unit_of_work import UnitOfWork
    from backend.app.models.operations import WorkerHeartbeat

    factory = sessionmaker(bind=database_engine)
    workers = [WorkerRuntime("collector", uow_factory=lambda: UnitOfWork(factory)) for _ in range(2)]
    barrier = Barrier(2)
    def claim(worker):
        barrier.wait(timeout=3)
        return worker.claim()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sum(pool.map(claim, workers)) == 1
    finally:
        with database_engine.begin() as connection:
            connection.execute(delete(WorkerHeartbeat).where(
                WorkerHeartbeat.worker_name == "collector",
                WorkerHeartbeat.lease_token.in_([worker.token for worker in workers]),
            ))
