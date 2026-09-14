"""Explicit positive-only imports into existing ingestion and discovery."""

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.ingestion.adapters import SourceAdapterRegistry
from backend.app.ingestion.aggregators import (
    SOURCES,
    StructuredObservationAdapter,
    load_observations,
)
from backend.app.ingestion.source_detection import detect_source
from backend.app.repositories.live_job_ingestion import LiveJobIngestionRepository
from backend.app.services.job_ingestion import JobIngestionService, normalize_company_identity
from backend.app.services.source_intelligence import enqueue_urls


def import_observations(path, *, uow_factory=UnitOfWork):
    records = load_observations(path)
    registry = SourceAdapterRegistry(StructuredObservationAdapter(key) for key in SOURCES)
    count = 0
    for record in records:
        with uow_factory() as uow:
            LiveJobIngestionRepository(uow.session).ensure_configured_catalog(
                normalize_company_identity(record.company), record.role
            )
            uow.session.flush()
            JobIngestionService.ingest_with_outcome(record, registry, uow)
        count += 1
        # Only queue detected ATS destinations; never crawl aggregator listing pages.
        config = detect_source(record.application_url, record.company)
        if config is not None:
            from backend.app.services.source_seeds import canonical_board_url

            board = canonical_board_url(config)
            enqueue_urls(
                (record.model_copy(update={"application_url": board, "source_url": board}),),
                record.adapter_key,
                uow_factory,
            )
    return {"observations": count}
