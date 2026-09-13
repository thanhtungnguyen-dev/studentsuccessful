"""Check the durable heartbeat for one production background worker."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.services.worker_runtime import worker_health


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("worker", choices=("collector", "alert-worker"))
    args = parser.parse_args(argv)
    try:
        with UnitOfWork() as uow:
            state = worker_health(args.worker, session=uow.session)
    except Exception:
        print(f"worker={args.worker} status=unavailable")
        return 1
    print(
        f"worker={state.worker_name} status={state.status} "
        f"last_heartbeat={state.last_heartbeat_at or '-'} "
        f"last_completed={state.last_completed_at or '-'}"
    )
    return 0 if state.status == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
