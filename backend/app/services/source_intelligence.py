"""Bounded source expansion on the existing collector, with short transactions."""

import hashlib
import json
import logging
from datetime import timedelta

import httpx
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.ingestion.live import LiveJobSourceConfig, create_live_adapter
from backend.app.ingestion.public_http import public_get, public_url
from backend.app.ingestion.source_detection import detect_source, source_identity
from backend.app.models.base import utc_now
from backend.app.models.intelligence import SourceDiscoveryWork, SourceFetchEvidence, SourceRegistry

logger = logging.getLogger("studentsuccessful.discovery")


def effective_sources(seeds, uow_factory=UnitOfWork, *, include_discovered=True):
    """Configured identities win, including disabled seeds; persisted discoveries survive restarts."""
    by_identity = {}
    with uow_factory() as uow:
        uow.session.execute(text("SELECT pg_advisory_xact_lock(260001)"))
        for config in seeds:
            identity = (config.family, source_identity(config))
            by_identity.setdefault(identity, config)
            existing = uow.session.scalar(
                select(SourceRegistry).where(
                    SourceRegistry.provider == config.family, SourceRegistry.identity == identity[1]
                )
            )
            if existing:
                # Never reactivate a discovered alias when a seed is disabled/removed.
                existing.configuration = config.model_dump(mode="json")
                existing.origin = "CONFIGURED"
                existing.enabled = config.enabled
            else:
                owner = uow.session.get(SourceRegistry, config.key)
                if owner and (owner.provider, owner.identity) != identity:
                    raise ValueError("Source key cannot be reassigned to a different board")
                uow.session.execute(
                    insert(SourceRegistry)
                    .values(
                        source_key=config.key,
                        provider=config.family,
                        identity=identity[1],
                        configuration=config.model_dump(mode="json"),
                        origin="CONFIGURED",
                        enabled=config.enabled,
                    )
                    .on_conflict_do_nothing()
                )
        if include_discovered:
            for row in uow.session.scalars(
                select(SourceRegistry).order_by(SourceRegistry.source_key).limit(1000)
            ):
                config = LiveJobSourceConfig.model_validate(row.configuration).model_copy(
                    update={"enabled": row.enabled}
                )
                if any(seed.key == config.key for seed in seeds):
                    continue
                by_identity.setdefault((row.provider, row.identity), config)
        uow.commit()
    return tuple(by_identity.values())


def enqueue_urls(records, parent_source, uow_factory=UnitOfWork):
    with uow_factory() as uow:
        uow.session.execute(text("SELECT pg_advisory_xact_lock(260002)"))
        # Bound historical suppression while allowing the network to expand after restart.
        uow.session.execute(
            delete(SourceDiscoveryWork).where(
                SourceDiscoveryWork.state != "PENDING",
                SourceDiscoveryWork.due_at < utc_now() - timedelta(days=30),
            )
        )
        available = max(
            0, 5000 - uow.session.scalar(select(func.count()).select_from(SourceDiscoveryWork))
        )
        for record in records:
            for url in (record.application_url, record.source_url):
                if available == 0:
                    break
                try:
                    public_url(url)
                    # Query-bearing unknown URLs may carry access tokens. Never queue them.
                    from urllib.parse import urlsplit

                    if urlsplit(url).query:
                        continue
                except ValueError:
                    continue
                key = hashlib.sha256(url.encode()).hexdigest()
                result = uow.session.execute(
                    insert(SourceDiscoveryWork)
                    .values(
                        url_hash=key, url=url, company=record.company, parent_source=parent_source
                    )
                    .on_conflict_do_nothing()
                )
                available -= result.rowcount
        uow.commit()


def process_discovery(
    *,
    uow_factory=UnitOfWork,
    now=utc_now,
    fetch=public_get,
    adapter_factory=create_live_adapter,
    limit=3,
):
    """Lease at most three URLs per cycle, verify outside transactions, register idempotently."""
    outcomes = []
    for _ in range(min(limit, 3)):
        clock = now()
        with uow_factory() as uow:
            from sqlalchemy import update

            uow.session.execute(
                update(SourceDiscoveryWork)
                .where(
                    SourceDiscoveryWork.state == "PENDING",
                    SourceDiscoveryWork.attempts == 3,
                    SourceDiscoveryWork.due_at <= clock,
                )
                .values(state="FAILED")
            )
            work = uow.session.scalar(
                select(SourceDiscoveryWork)
                .where(
                    SourceDiscoveryWork.state == "PENDING",
                    SourceDiscoveryWork.attempts < 3,
                    SourceDiscoveryWork.due_at <= clock,
                )
                .order_by(SourceDiscoveryWork.due_at, SourceDiscoveryWork.url_hash)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if work is None:
                uow.commit()
                break
            url, company, key = work.url, work.company, work.url_hash
            work.attempts += 1
            attempt = work.attempts
            work.due_at = clock + timedelta(minutes=10)
            uow.commit()
        config = None
        status = "UNKNOWN"
        try:
            config = detect_source(url, company)
            if config is None:
                response = fetch(url, timeout=5)
                if response.status_code == 429 or response.status_code >= 500:
                    raise ValueError("Temporary discovery failure")
                if response.status_code == 200:
                    from backend.app.ingestion.source_detection import detect_content

                    config = detect_content(str(response.url), company, response.text)
            if config:
                with uow_factory() as uow:
                    known = uow.session.scalar(
                        select(SourceRegistry.source_key).where(
                            SourceRegistry.provider == config.family,
                            SourceRegistry.identity == source_identity(config),
                        )
                    )
                if known:
                    status = "VERIFIED"
                else:
                    result = adapter_factory(
                        config.model_copy(update={"max_postings": 2}), timeout_seconds=5
                    ).fetch_with_metadata()
                    if result.skipped_records or result.not_modified:
                        raise ValueError("Source could not be verified")
                    status = "VERIFIED"
        except Exception:
            status = "FAILED" if attempt == 3 else "PENDING"
        with uow_factory() as uow:
            work = uow.session.get(SourceDiscoveryWork, key, with_for_update=True)
            if work.attempts != attempt:
                continue
            if status == "VERIFIED":
                uow.session.execute(text("SELECT pg_advisory_xact_lock(260001)"))
                if uow.session.scalar(select(func.count()).select_from(SourceRegistry)) < 1000:
                    statement = insert(SourceRegistry).values(
                        source_key=config.key,
                        provider=config.family,
                        identity=source_identity(config),
                        configuration=config.model_dump(mode="json"),
                        origin="DISCOVERED",
                        enabled=True,
                        discovered_from=url,
                    )
                    uow.session.execute(statement.on_conflict_do_nothing())
                    row = uow.session.scalar(
                        select(SourceRegistry).where(
                            SourceRegistry.provider == config.family,
                            SourceRegistry.identity == source_identity(config),
                        )
                    )
                    work.result_source = row.source_key if row else None
                else:
                    status = "FAILED"
            work.state = status
            work.due_at = now() + timedelta(seconds=300 * 2**attempt)
            uow.commit()
        outcomes.append(status)
    return outcomes


def preserve_fetch(adapter, uow_factory=UnitOfWork):
    pages = getattr(adapter, "evidence_pages", [])
    if not pages or getattr(adapter, "evidence_truncated", False):
        return None
    encoded = json.dumps(pages, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode()) > 10 * 1024 * 1024:
        logger.warning("fetch_evidence_budget_exceeded")
        return None
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    with uow_factory() as uow:
        uow.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 26))"), {"key": adapter.key}
        )
        statement = insert(SourceFetchEvidence).values(
            source_key=adapter.key,
            content_hash=digest,
            parser_version=getattr(adapter, "evidence_parser_version", "structured-v2"),
            configuration=adapter.config.model_dump(mode="json"),
            pages=pages,
        )
        uow.session.execute(
            statement.on_conflict_do_update(
                index_elements=["source_key", "content_hash"], set_={"last_fetched_at": utc_now()}
            )
        )
        # Retain only the latest ten distinct fetches per source, independent of observation snapshots.
        old = (
            select(SourceFetchEvidence.content_hash)
            .where(SourceFetchEvidence.source_key == adapter.key)
            .order_by(SourceFetchEvidence.last_fetched_at.desc(), SourceFetchEvidence.content_hash)
            .offset(10)
        )
        uow.session.execute(
            delete(SourceFetchEvidence).where(
                SourceFetchEvidence.source_key == adapter.key,
                SourceFetchEvidence.content_hash.in_(old),
            )
        )
        uow.commit()
    return digest


def replay_fetch(source_key, digest, uow_factory=UnitOfWork):
    """Parse stored evidence without network or lifecycle/alert side effects; return DTOs."""
    with uow_factory() as uow:
        row = uow.session.get(SourceFetchEvidence, (source_key, digest))
        if row is None:
            raise ValueError("Unknown fetch evidence")
        config = LiveJobSourceConfig.model_validate(row.configuration)
        pages = list(row.pages)
        parser_version = row.parser_version
    if parser_version == "greenhouse-detail-v1":
        from backend.app.ingestion.live import LiveFetchResult

        if config.family != "greenhouse" or len(pages) != 1:
            raise ValueError("Invalid Greenhouse detail evidence")
        adapter = create_live_adapter(config)
        record = adapter._parse_record(json.loads(pages[0]["content"]))
        return LiveFetchResult((record,), 1, 0, 0, False, 200, None, None, False)

    def handler(request):
        if not pages:
            raise ValueError("Replay is missing a response; network is forbidden")
        page = pages.pop(0)
        if str(request.url) != page["url"]:
            raise ValueError("Replay request differs from captured evidence")
        return httpx.Response(
            page["status"], text=page["content"], headers={"content-type": page["content_type"]}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return create_live_adapter(config, client=client).fetch_with_metadata()
