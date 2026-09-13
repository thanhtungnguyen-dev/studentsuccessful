"""Run durable Phase 23 alert reconciliation and in-app delivery.

Examples:
    python -m backend.app.commands.process_job_alerts once
    python -m backend.app.commands.process_job_alerts run
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass

from backend.app.core.logging import configure_logging
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.services.job_alerts import AlertDeliveryService, JobAlertService
from backend.app.services.worker_runtime import WorkerRuntime

logger = logging.getLogger("studentsuccessful.alert_worker")


@dataclass(frozen=True)
class AlertWorkerCycle:
    scanned: int
    created: int
    delivered: int
    suppressed: int
    retried: int
    failed: int


class JobAlertWorker:
    """A small PostgreSQL-backed worker; all critical state remains durable."""

    def __init__(self, uow_factory=UnitOfWork) -> None:
        self._uow_factory = uow_factory

    def run_once(self) -> AlertWorkerCycle:
        with self._uow_factory() as uow:
            evaluation = JobAlertService.reconcile(uow.session)
            delivery = AlertDeliveryService.deliver_due(uow.session)
            uow.commit()
        return AlertWorkerCycle(
            scanned=evaluation.scanned,
            created=evaluation.created,
            delivered=delivery.delivered,
            suppressed=delivery.suppressed,
            retried=delivery.retried,
            failed=delivery.failed,
        )

    def run_forever(self, stop_event: threading.Event | None = None) -> int:
        stop_event = stop_event or threading.Event()
        runtime = WorkerRuntime("alert-worker")
        standby_logged = False
        try:
            while not stop_event.is_set():
                if not runtime.owns_lease:
                    if not runtime.claim():
                        if not standby_logged:
                            logger.info(
                                "worker_lease_held",
                                extra={"event": "worker_lease_held", "worker": "alert-worker"},
                            )
                            standby_logged = True
                        stop_event.wait(5)
                        continue
                    standby_logged = False
                    logger.info(
                        "worker_started",
                        extra={"event": "worker_started", "worker": "alert-worker"},
                    )

                if not runtime.heartbeat():
                    logger.warning(
                        "worker_lease_lost",
                        extra={"event": "worker_lease_lost", "worker": "alert-worker"},
                    )
                    continue
                started = time.perf_counter()
                try:
                    cycle = self.run_once()
                except Exception:
                    logger.exception(
                        "alert_worker_cycle_failed",
                        extra={"event": "alert_worker_cycle_failed", "worker": "alert-worker"},
                    )
                    return 1
                if not runtime.heartbeat(completed=True):
                    logger.warning(
                        "worker_lease_lost",
                        extra={"event": "worker_lease_lost", "worker": "alert-worker"},
                    )
                    continue
                logger.info(
                    "alert_worker_cycle_completed",
                    extra={
                        "event": "alert_worker_cycle_completed",
                        "worker": "alert-worker",
                        "scanned": cycle.scanned,
                        "alerts_created": cycle.created,
                        "delivered": cycle.delivered,
                        "suppressed": cycle.suppressed,
                        "retried": cycle.retried,
                        "failed": cycle.failed,
                        "duration_ms": round((time.perf_counter() - started) * 1000),
                    },
                )
                stop_event.wait(30)
        finally:
            runtime.release()
        return 0


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("once", "run"))
    return parser.parse_args(argv)


def _print_cycle(cycle: AlertWorkerCycle) -> None:
    print(
        "scanned="
        f"{cycle.scanned} created={cycle.created} delivered={cycle.delivered} "
        f"suppressed={cycle.suppressed} retried={cycle.retried} failed={cycle.failed}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    args = _arguments(argv)
    worker = JobAlertWorker()
    if args.command == "once":
        _print_cycle(worker.run_once())
        return 0

    stop_event = threading.Event()

    def request_stop(signum, frame) -> None:
        del signum, frame
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    print("Job alert worker started. Press Ctrl+C to stop.")
    result = worker.run_forever(stop_event)
    print("Job alert worker stopped.")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
