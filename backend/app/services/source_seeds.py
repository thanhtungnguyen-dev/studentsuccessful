"""Explicit offline corpus validation and idempotent registry import."""

import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select, text

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.ingestion.source_detection import detect_source, source_identity
from backend.app.models.intelligence import SourceRegistry

DEFAULT_SEEDS = Path(__file__).resolve().parents[2] / "data" / "job_source_seeds.json"


def canonical_board_url(config):
    base = {
        "greenhouse": f"https://boards.greenhouse.io/{config.board_token}",
        "lever": f"https://jobs.{'eu.' if config.region == 'eu' else ''}lever.co/{config.site}",
        "ashby": f"https://jobs.ashbyhq.com/{config.job_board}",
        "smartrecruiters": f"https://jobs.smartrecruiters.com/{config.company_identifier}",
    }.get(config.family, config.public_board_url or config.feed_url)
    p = urlsplit(base)
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", ""))


def load_seeds(path=DEFAULT_SEEDS):
    path = Path(path)
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Seed corpus exceeds limit")
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
        raise ValueError("Expected 1-500 seed records")
    identities, keys, result = set(), set(), []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {
            "key",
            "company",
            "provider",
            "url",
            "evidence",
            "geography",
        }:
            raise ValueError(f"Invalid seed fields at row {index}")
        if not all(isinstance(value, str) and value for value in row.values()):
            raise ValueError(f"Invalid seed values at row {index}")
        p = urlsplit(row["url"])
        if p.scheme != "https" or p.query or p.fragment or p.username or p.password:
            raise ValueError(f"Unsafe seed URL at row {index}")
        config = detect_source(row["url"], row["company"])
        if config is None or config.family != row["provider"]:
            raise ValueError(f"Unsupported provider or hostname at row {index}")
        if canonical_board_url(config) != row["url"]:
            raise ValueError(f"Noncanonical board URL at row {index}")
        config = config.model_copy(update={"key": row["key"]})
        config = type(config).model_validate(config.model_dump())
        identity = (config.family, source_identity(config))
        if config.key in keys or identity in identities:
            raise ValueError("Duplicate seed key or provider identity")
        keys.add(config.key)
        identities.add(identity)
        if row["geography"] not in {"Canada", "United States", "Other/Unknown"}:
            raise ValueError("Invalid geography")
        if not isinstance(row["evidence"], str) or not row["evidence"]:
            raise ValueError("Seed requires evidence")
        result.append(config)
    if [c.key for c in result] != sorted(keys):
        raise ValueError("Seeds must be sorted by key")
    return tuple(result)


def import_seeds(path=DEFAULT_SEEDS, *, dry_run=False, uow_factory=UnitOfWork):
    configs = load_seeds(path)
    counts = dict(new=0, existing=0, updated=0, skipped=0, invalid=0, duplicate=0)
    with uow_factory() as uow:
        uow.session.execute(text("SELECT pg_advisory_xact_lock(260001)"))
        for config in configs:
            identity = source_identity(config)
            row = uow.session.scalar(
                select(SourceRegistry).where(
                    SourceRegistry.provider == config.family, SourceRegistry.identity == identity
                )
            )
            if row is not None:
                counts["existing"] += 1
                # Retain persisted key, operator enablement, polling and runtime choices.
                data = dict(row.configuration)
                if data.get("company") != config.company:
                    data["company"] = config.company
                    counts["updated"] += 1
                    if not dry_run:
                        row.configuration = data
                continue
            if uow.session.get(SourceRegistry, config.key) is not None:
                raise ValueError("Seed key belongs to a different board")
            counts["new"] += 1
            if not dry_run:
                uow.session.add(
                    SourceRegistry(
                        source_key=config.key,
                        provider=config.family,
                        identity=identity,
                        configuration=config.model_dump(mode="json"),
                        origin="CONFIGURED",
                        enabled=True,
                    )
                )
        if not dry_run:
            uow.commit()
    return counts


def verify_seeds(path=DEFAULT_SEEDS, *, limit=30, timeout=10):
    """Explicit read-only diverse sample; never writes registry or lifecycle."""
    from collections import Counter, defaultdict
    from concurrent.futures import ThreadPoolExecutor

    from backend.app.ingestion.public_http import public_get
    from backend.app.services.coverage_calibration import _probe

    load_seeds(path)
    grouped = defaultdict(list)
    for row in json.loads(Path(path).read_text(encoding="utf-8")):
        grouped[row["provider"]].append(row)
    sample = []
    while grouped and len(sample) < min(max(1, limit), 50):
        for family in sorted(list(grouped)):
            if len(sample) >= min(max(1, limit), 50):
                break
            sample.append(grouped[family].pop(0))
            if not grouped[family]:
                del grouped[family]

    def probe(row):
        result, _ = _probe(
            row, live=True, base=Path(path).parent, timeout=timeout, fetch=public_get
        )
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(probe, sample))
    counts = Counter(r["status"] for r in results)
    return {
        "attempted": len(results),
        "successful": counts["SUCCESS"],
        "valid_empty": counts["VALID_EMPTY_SOURCE"],
        "failed": len(results) - counts["SUCCESS"] - counts["VALID_EMPTY_SOURCE"],
        "jobs_observed": sum(r["jobs"] for r in results),
        "sources": results,
    }
