"""Run the durable Phase 19 live-source collector.

Examples:
    python -m backend.app.commands.collect_live once --all
    python -m backend.app.commands.collect_live run
    python -m backend.app.commands.collect_live health
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading
import time
from collections.abc import Sequence

from backend.app.core.config import settings
from backend.app.core.logging import configure_logging
from backend.app.ingestion.live import (
    LIVE_SOURCE_FAMILIES,
    LiveJobSourceConfig,
    LiveSourceConfigurationError,
    load_live_source_configs,
)
from backend.app.services.live_collection import LiveCollectionService
from backend.app.services.worker_runtime import WorkerRuntime

logger = logging.getLogger("studentsuccessful.collector")


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("once", "run", "health"))
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--all", action="store_true", help="select every configured source")
    selector.add_argument("--source", help="select one configured source key")
    selector.add_argument(
        "--family",
        choices=LIVE_SOURCE_FAMILIES,
        help="select every configured source in one ATS family",
    )
    return parser.parse_args(argv)


def _selected_configs(
    configs: tuple[LiveJobSourceConfig, ...], args: argparse.Namespace
) -> tuple[LiveJobSourceConfig, ...]:
    if args.source:
        selected = tuple(config for config in configs if config.key == args.source)
        if not selected:
            raise LiveSourceConfigurationError("requested source is not configured")
        return selected
    if args.family:
        return tuple(config for config in configs if config.family == args.family)
    return configs


def _service(configs: tuple[LiveJobSourceConfig, ...]) -> LiveCollectionService:
    return LiveCollectionService(
        configs,
        default_timeout_seconds=settings.LIVE_JOB_HTTP_TIMEOUT_SECONDS,
        max_concurrency=settings.LIVE_COLLECTOR_CONCURRENCY,
        max_backoff_seconds=settings.LIVE_COLLECTOR_MAX_BACKOFF_SECONDS,
    )


def _print_health(service: LiveCollectionService) -> None:
    for state in service.health_snapshots():
        failure_rate = (
            state.total_collection_failures / state.total_collection_attempts
            if state.total_collection_attempts
            else 0
        )
        print(
            f"source={state.source_key} family={state.family} enabled={str(state.enabled).lower()} "
            f"health={state.health} last_success={state.last_success_at or '-'} "
            f"next_poll={state.next_poll_at or '-'} failures={state.consecutive_failures} "
            f"last_error={state.last_error_category or '-'} "
            f"observed={state.total_jobs_observed} new_canonical={state.total_new_canonical_jobs} "
            f"duplicates={state.total_duplicate_contributions} "
            f"student_roles={state.total_internship_or_coop_contributions} "
            f"official_apply={state.total_official_apply_urls} "
            f"failure_rate={failure_rate:.3f} last_new={state.last_new_canonical_job_at or '-'}"
        )


def _run_forever(service: LiveCollectionService, *, once=False, stop_event=None, runtime=None) -> int:
    stop_event = stop_event or threading.Event()
    runtime = runtime or WorkerRuntime("collector")
    failures = 0
    previous_handlers = {}

    def request_stop(signum, frame):
        stop_event.set()

    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, request_stop)
    try:
        while not stop_event.is_set():
            cycle_stop = threading.Event()

            def tick():
                if stop_event.is_set():
                    cycle_stop.set()
                if not runtime.heartbeat():
                    raise RuntimeError("Collector worker lease lost")

            try:
                if not runtime.owns_lease and not runtime.claim():
                    logger.info("worker_lease_held", extra={"worker": "collector"})
                    if once:
                        return 1
                    stop_event.wait(5)
                    continue
                tick()
                started = time.perf_counter()
                cycle = service.run_cycle(force=False, stop_event=cycle_stop, on_tick=tick)
                if not runtime.heartbeat(completed=True):
                    raise RuntimeError("Collector worker lease lost")
                logger.info(
                    "collector_cycle_completed",
                    extra={"event": "collector_cycle_completed", "worker": "collector",
                           "attempted": cycle.attempted, "failed": cycle.failed,
                           "duration_ms": round((time.perf_counter() - started) * 1000)},
                )
                if once:
                    return 1 if cycle.failed else 0
                delay = min(20, service.seconds_until_next_poll(), runtime.lease_seconds // 3)
                failures = 0
                stop_event.wait(max(1, delay))
            except Exception:
                cycle_stop.set()
                failures += 1
                logger.exception("collector_retry", extra={"event": "collector_retry", "worker": "collector"})
                if once:
                    return 1
                stop_event.wait(min(60, 5 * (2 ** min(failures - 1, 4))))
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        try:
            runtime.release()
        except Exception:
            logger.exception("worker_release_failed", extra={"worker": "collector"})
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)
    logger.info("worker_stopped", extra={"worker": "collector"})
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    args = _arguments(argv)
    try:
        configs = _selected_configs(load_live_source_configs(settings.LIVE_JOB_SOURCES_JSON), args)
        service = _service(configs)
        service.include_discovered = not (args.source or args.family)
    except (LiveSourceConfigurationError, ValueError) as exc:
        print(f"Configuration error: {exc}")
        return 2

    from backend.app.core.database import engine

    try:
        if args.command == "health":
            service.synchronize()
            _print_health(service)
            return 0
        return _run_forever(service, once=args.command == "once")
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
