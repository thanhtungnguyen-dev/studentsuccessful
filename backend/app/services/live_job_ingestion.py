"""Operational orchestration for configured public job-board fetches."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.ingestion.adapters import SourceAdapterRegistry
from backend.app.ingestion.job_scope import geography, scoped_records
from backend.app.ingestion.live import LiveFetchResult, LiveSourceAdapter
from backend.app.repositories.live_job_ingestion import LiveJobIngestionRepository
from backend.app.services.job_ingestion import JobIngestionService, JobIngestionValidationError


@dataclass(frozen=True)
class LiveSourceIngestionResult:
    source_key: str
    family: str
    fetched: int
    parsed: int
    ingested: int
    malformed: int
    rejected: int
    filtered: int
    scope_filtered: int = 0
    jobs_ca: int = 0
    jobs_us: int = 0
    jobs_north_america: int = 0
    not_modified: bool = False
    http_status: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    complete_listing: bool = False
    observed_external_ids: tuple[str, ...] = ()
    new_canonical_jobs: int = 0
    duplicate_contributions: int = 0
    internship_or_coop_contributions: int = 0
    official_apply_urls: int = 0
    content_hash: str | None = None
    content_fingerprints: tuple[tuple[str, str], ...] = ()


class LiveJobIngestionService:
    """Fetch once, then commit every valid public posting independently.

    The database write for each record is still the existing Phase 10 service.
    Per-record UoWs make an invalid provider item unable to roll back another
    posting that has already committed successfully.
    """

    @staticmethod
    def ingest_adapter(
        adapter: LiveSourceAdapter,
        registry: SourceAdapterRegistry,
        *,
        fetch_result: LiveFetchResult | None = None,
        uow_factory: Callable[[], UnitOfWork] = UnitOfWork,
    ) -> LiveSourceIngestionResult:
        fetched = fetch_result or adapter.fetch_with_metadata()
        records = scoped_records(fetched.records)
        countries = Counter(geography(r.locations) for r in records)
        from backend.app.core.config import settings
        from backend.app.services.source_intelligence import enqueue_urls, preserve_fetch

        preserve_fetch(adapter, uow_factory)
        fingerprints = tuple(
            sorted(
                (
                    record.external_id,
                    hashlib.sha256(
                        json.dumps(
                            record.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
                        ).encode()
                    ).hexdigest(),
                )
                for record in records
            )
        )
        content_hash = None if fetched.not_modified else scoped_content_hash(fingerprints)
        if records:
            with uow_factory() as uow:
                for role in sorted({record.role for record in records}):
                    LiveJobIngestionRepository(uow.session).ensure_configured_catalog(
                        adapter.config.company, role
                    )
                uow.commit()

        ingested = 0
        rejected = 0
        new_canonical_jobs = 0
        duplicate_contributions = 0
        internship_or_coop_contributions = 0
        official_apply_urls = 0
        for record in records:
            try:
                with uow_factory() as uow:
                    outcome = JobIngestionService.ingest_with_outcome(record, registry, uow)
                ingested += 1
                if outcome.source_observation_created:
                    if outcome.canonical_created:
                        new_canonical_jobs += 1
                    else:
                        duplicate_contributions += 1
                    if record.employment_type in {"INTERNSHIP", "CO_OP"}:
                        internship_or_coop_contributions += 1
                    if adapter.source_authority in {"OFFICIAL_COMPANY", "OFFICIAL_ATS"}:
                        official_apply_urls += 1
            except JobIngestionValidationError:
                rejected += 1

        if settings.LIVE_SOURCE_DISCOVERY_ENABLED:
            try:
                enqueue_urls(records, adapter.key, uow_factory)
            except Exception:
                import logging

                logging.getLogger("studentsuccessful.discovery").warning("discovery_enqueue_failed")
        return LiveSourceIngestionResult(
            source_key=adapter.key,
            family=adapter.family,
            fetched=fetched.fetched_records,
            parsed=len(records),
            ingested=ingested,
            malformed=fetched.skipped_records,
            rejected=rejected,
            filtered=fetched.filtered_records,
            scope_filtered=len(fetched.records) - len(records),
            jobs_ca=countries["CA"],
            jobs_us=countries["US"],
            jobs_north_america=countries["NORTH_AMERICA"],
            not_modified=fetched.not_modified,
            http_status=fetched.http_status,
            etag=fetched.etag,
            last_modified=fetched.last_modified,
            complete_listing=fetched.complete_listing,
            observed_external_ids=tuple(record.external_id for record in records),
            new_canonical_jobs=new_canonical_jobs,
            duplicate_contributions=duplicate_contributions,
            internship_or_coop_contributions=internship_or_coop_contributions,
            official_apply_urls=official_apply_urls,
            content_hash=content_hash,
            content_fingerprints=fingerprints,
        )


def scoped_content_hash(fingerprints):
    """One bounded accepted-record signal, independent of provider batch boundaries."""
    return hashlib.sha256(
        json.dumps(sorted(fingerprints), separators=(",", ":")).encode()
    ).hexdigest()


__all__ = ["LiveJobIngestionService", "LiveSourceIngestionResult"]
