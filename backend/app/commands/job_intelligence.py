"""Read-only intelligence diagnostics and offline fetch replay."""

import argparse
import json

from sqlalchemy import func, select

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.models.intelligence import SourceDiscoveryWork, SourceFetchEvidence, SourceRegistry
from backend.app.services.source_intelligence import replay_fetch
from backend.app.services.source_quality import quality_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["report", "replay", "coverage-calibrate"])
    parser.add_argument("--source")
    parser.add_argument("--hash")
    parser.add_argument("--fixture")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--provider")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    if args.command == "coverage-calibrate":
        from backend.app.services.coverage_calibration import DEFAULT_FIXTURE, calibrate

        try:
            report = calibrate(
                args.fixture or DEFAULT_FIXTURE,
                live=args.live,
                limit=args.limit,
                provider=args.provider,
                concurrency=args.concurrency,
                timeout=args.timeout,
            )
        except (ValueError, OSError, KeyError) as error:
            parser.error(str(error))
        if args.json:
            print(json.dumps(report, sort_keys=True))
        else:
            print(
                f"{report['mode']}: {report['sources_probed']} probes; {report['jobs_observed']} sampled jobs; database writes: 0"
            )
            for row in report["sources"]:
                print(
                    f"{row['company']} | {row['provider'] or 'unknown'} | {row['status']} | {row['jobs']}"
                )
        return
    if args.command == "replay":
        result = replay_fetch(args.source, args.hash)
        print(
            json.dumps(
                {"parsed": len(result.records), "malformed": result.skipped_records, "writes": 0}
            )
        )
        return
    with UnitOfWork() as uow:
        report = quality_report(uow.session)
        report["fetch_evidence"] = [
            dict(source=row.source_key, hash=row.content_hash, fetched_at=row.last_fetched_at)
            for row in uow.session.execute(
                select(
                    SourceFetchEvidence.source_key,
                    SourceFetchEvidence.content_hash,
                    SourceFetchEvidence.last_fetched_at,
                )
                .order_by(SourceFetchEvidence.last_fetched_at.desc())
                .limit(100)
            )
        ]
        report["discovery"] = dict(
            uow.session.execute(
                select(SourceDiscoveryWork.state, func.count()).group_by(SourceDiscoveryWork.state)
            ).all()
        )
        report["registry"] = [
            dict(
                source=row.source_key, provider=row.provider, origin=row.origin, enabled=row.enabled
            )
            for row in uow.session.scalars(select(SourceRegistry))
        ]
        print(json.dumps(report, default=str))


if __name__ == "__main__":
    main()
