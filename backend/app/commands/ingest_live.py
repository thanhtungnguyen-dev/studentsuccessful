"""Fetch configured public ATS boards through the existing job-ingestion service.

Examples:
    python -m backend.app.commands.ingest_live --all
    python -m backend.app.commands.ingest_live --source greenhouse.example
    python -m backend.app.commands.ingest_live --family lever
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from backend.app.core.config import settings
from backend.app.ingestion.adapters import SourceAdapterRegistry
from backend.app.ingestion.live import (
    LIVE_SOURCE_FAMILIES,
    LiveJobSourceConfig,
    LiveSourceConfigurationError,
    LiveSourceFetchError,
    create_live_adapter,
    load_live_source_configs,
)
from backend.app.services.live_job_ingestion import LiveJobIngestionService


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--all", action="store_true", help="ingest every enabled configured source")
    selector.add_argument("--source", help="ingest one enabled source key")
    selector.add_argument(
        "--family",
        choices=LIVE_SOURCE_FAMILIES,
        help="ingest every enabled source in one ATS family",
    )
    return parser.parse_args(argv)


def _selected_sources(
    configs: tuple[LiveJobSourceConfig, ...], args: argparse.Namespace
) -> tuple[LiveJobSourceConfig, ...]:
    enabled = tuple(config for config in configs if config.enabled)
    if args.source:
        selected = tuple(config for config in enabled if config.key == args.source)
        if not selected:
            raise LiveSourceConfigurationError("requested source is not an enabled configured source")
        return selected
    if args.family:
        return tuple(config for config in enabled if config.family == args.family)
    return enabled


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    try:
        configs = load_live_source_configs(settings.LIVE_JOB_SOURCES_JSON)
        selected = _selected_sources(configs, args)
    except LiveSourceConfigurationError as exc:
        print(f"Configuration error: {exc}")
        return 2

    if not selected:
        print("No enabled live job sources are configured.")
        return 0
    if settings.LIVE_JOB_HTTP_TIMEOUT_SECONDS <= 0:
        print("Configuration error: LIVE_JOB_HTTP_TIMEOUT_SECONDS must be positive")
        return 2

    adapters = tuple(
        create_live_adapter(config, timeout_seconds=settings.LIVE_JOB_HTTP_TIMEOUT_SECONDS)
        for config in selected
    )
    registry = SourceAdapterRegistry(adapters)
    failed = False
    for adapter in adapters:
        try:
            result = LiveJobIngestionService.ingest_adapter(adapter, registry)
        except (LiveSourceConfigurationError, LiveSourceFetchError, ValueError) as exc:
            failed = True
            print(f"source={adapter.key} family={adapter.family} status=failed detail={exc}")
            continue
        print(
            f"source={result.source_key} family={result.family} fetched={result.fetched} "
            f"parsed={result.parsed} ingested={result.ingested} malformed={result.malformed} "
            f"scope_filtered={result.scope_filtered} CA={result.jobs_ca} US={result.jobs_us} NA={result.jobs_north_america} "
            f"rejected={result.rejected} filtered={result.filtered} "
            f"new_canonical={result.new_canonical_jobs} "
            f"duplicates={result.duplicate_contributions}"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
