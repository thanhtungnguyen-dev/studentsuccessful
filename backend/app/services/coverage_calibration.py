"""Bounded read-only source calibration. No sessions, registration, or ingestion writes."""

import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from backend.app.ingestion.live import LiveSourceFetchError, create_live_adapter
from backend.app.ingestion.normalization import remote_scope
from backend.app.ingestion.public_http import public_get, public_url
from backend.app.ingestion.source_detection import detect_content, detect_source, source_identity
from backend.app.services.canonical_jobs import canonical_url_fingerprint

DEFAULT_FIXTURE = Path(__file__).resolve().parents[2] / "calibration" / "sources.json"
FIELDS = (
    "title",
    "company",
    "description",
    "location",
    "employment_type",
    "work_mode",
    "posted_at",
    "updated_at",
    "apply_url",
)


def error_category(error):
    chain = []
    current = error
    while current is not None and len(chain) < 8:
        chain.append(current)
        current = current.__cause__
    for item in chain:
        if isinstance(item, httpx.TimeoutException):
            return "TIMEOUT"
        if isinstance(item, httpx.ConnectError) and "DNS" in str(item):
            return "DNS_ERROR"
        if isinstance(item, ValueError):
            message = str(item).lower()
            if "too large" in message or "compressed" in message:
                return "INVALID_RESPONSE"
            if "redirect" in message or "downgrade" in message:
                return "REDIRECT_FAILURE"
            if any(
                word in message
                for word in ("unsafe", "private", "nonpublic", "nonstandard", "credential")
            ):
                return "NETWORK_SAFETY_REJECTION"
    if isinstance(error, LiveSourceFetchError):
        status = error.status_code
        if status in {403, 404, 429}:
            return f"HTTP_{status}"
        if status and status >= 500:
            return "HTTP_5XX"
        if error.category == "TIMEOUT":
            return "TIMEOUT"
        if error.category in {"MALFORMED_RESPONSE", "OVERSIZED_RESPONSE"}:
            return "INVALID_RESPONSE"
        if status:
            return "HTTP_ERROR"
    if isinstance(error, (ValueError, TypeError)):
        return "INVALID_RESPONSE"
    return "NETWORK_ERROR"


def unknown_pattern(url):
    p = urlsplit(url)
    host = p.hostname or "invalid"
    family = "workday" if re.fullmatch(r"[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com", host) else None
    if host == "apply.workable.com" and p.path.startswith("/j/"):
        family = "workable-accountless"
    parts = [x for x in p.path.split("/") if x]
    # Only structural categories are reported, never query strings or arbitrary full paths.
    structure = (
        "/job/..."
        if "job" in parts
        else "/jobs/..."
        if "jobs" in parts
        else "/career-site"
        if family == "workday"
        else "/page"
    )
    return {
        "hostname": host,
        "url_structure": structure,
        "probable_family": family,
        "observed_jobs": None,
    }


def read_sources(path, limit, provider):
    path = Path(path)
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Calibration manifest too large")
    rows = json.loads(path.read_text(encoding="utf-8-sig"))["sources"]
    if not isinstance(rows, list) or len(rows) > 40:
        raise ValueError("Calibration set must contain at most 40 sources")
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("url"), str)
            or not isinstance(row.get("company"), str)
        ):
            raise ValueError("Invalid calibration source")
    return [row for row in rows if not provider or row.get("provider") == provider][:limit]


def _probe(row, *, live, base, timeout, fetch):
    result = {
        "company": row["company"],
        "provider": None,
        "identity": None,
        "status": "NOT_PROBED",
        "jobs": 0,
        "records_examined": 0,
        "malformed": 0,
        "complete_listing": False,
        "direct": False,
        "unknown_pattern": None,
        "requests": 0,
    }
    records = ()
    try:
        url = public_url(row["url"])
        config = detect_source(url, row["company"])
        if config is None:
            result["unknown_pattern"] = unknown_pattern(url)
        if config:
            result.update(provider=config.family, identity=source_identity(config))
        responses = {}
        if not live:
            fixture = row.get("fixture")
            if not fixture:
                return result, records
            path = (base / fixture).resolve()
            if not path.is_relative_to(base.resolve()) or path.stat().st_size > 10 * 1024 * 1024:
                raise ValueError("Unsafe fixture path or size")
            pages = json.loads(path.read_text(encoding="utf-8-sig"))["responses"]
            responses = {page["url"]: page for page in pages}
        memo = {}

        def request(target, *, redirects=0):
            public_url(target)
            if target in memo:
                return memo[target]
            if len(memo) >= 6:
                raise LiveSourceFetchError(
                    "Probe request budget exceeded", category="MALFORMED_RESPONSE"
                )
            result["requests"] += 1
            if live:
                response = fetch(target, timeout=timeout, redirects=redirects)
            else:
                page = responses.get(target)
                if page is None:
                    raise LiveSourceFetchError(
                        "Fixture response missing", category="MALFORMED_RESPONSE"
                    )
                response = httpx.Response(
                    page["status"],
                    text=page["content"],
                    headers={"content-type": page.get("content_type") or "text/plain"},
                    request=httpx.Request("GET", target),
                )
            memo[target] = response
            return response

        if config is None:
            response = request(url, redirects=3)
            if response.status_code != 200:
                raise LiveSourceFetchError("Probe HTTP failure", status_code=response.status_code)
            config = detect_content(str(response.url), row["company"], response.text)
            if config is None:
                result.update(
                    status="UNSUPPORTED_PROVIDER",
                    unknown_pattern=unknown_pattern(str(response.url)),
                )
                return result, records
        result.update(
            provider=config.family,
            identity=source_identity(config),
            unknown_pattern=None,
            direct=config.effective_source_authority in {"OFFICIAL_ATS", "OFFICIAL_COMPANY"},
        )
        # Five details plus list; Greenhouse may first reject one oversized response.
        config = config.model_copy(update={"max_postings": 5})

        def transport(req):
            response = request(str(req.url))
            return httpx.Response(
                response.status_code,
                content=response.content,
                headers={"content-type": response.headers.get("content-type", "")},
            )

        with httpx.Client(transport=httpx.MockTransport(transport)) as client:
            adapter = create_live_adapter(config, client=client, timeout_seconds=timeout)
            parsed = adapter.fetch_with_metadata()
            result["retrieval_strategy"] = getattr(adapter, "retrieval_strategy", "normal")
            result["continuation"] = parsed.continuation
        records = parsed.records
        result.update(
            jobs=len(records),
            records_examined=parsed.fetched_records,
            malformed=parsed.skipped_records,
            complete_listing=parsed.complete_listing,
        )
        if parsed.skipped_records:
            result["status"] = "PARSER_ERROR"
        elif not records and parsed.complete_listing and parsed.fetched_records == 0:
            result["status"] = "VALID_EMPTY_SOURCE"
        elif records:
            result["status"] = "SUCCESS"
        else:
            result["status"] = "INVALID_RESPONSE"
    except Exception as error:
        result["status"] = error_category(error)
        if isinstance(error, LiveSourceFetchError):
            result["failure_category"] = error.category
    return result, records


def record_metrics(items, now):
    grouped = defaultdict(list)
    for provider, item in items:
        grouped[provider].append(item)
    output = {}
    for provider, rows in sorted(grouped.items()):
        counts = Counter()
        ages = []
        for row in rows:
            values = {
                "title": row.title,
                "company": row.company if provider != "rss" else None,
                "description": row.description,
                "location": row.locations,
                "employment_type": row.employment_type != "UNSPECIFIED",
                "work_mode": row.work_mode != "UNSPECIFIED",
                "posted_at": row.posted_at,
                "updated_at": row.source_updated_at,
                "apply_url": row.application_url,
            }
            counts.update(key for key, value in values.items() if value)
            if row.posted_at and row.posted_at <= now:
                ages.append((now - row.posted_at).total_seconds())
        output[provider] = {
            "jobs": len(rows),
            "completeness": {key: round(counts[key] / len(rows), 4) for key in FIELDS},
            "posted_age_samples": len(ages),
            "posted_age_seconds_p50": _percentile(ages, 0.5),
            "posted_age_seconds_p95": _percentile(ages, 0.95),
        }
    return output


def _percentile(values, fraction):
    # Avoid presenting an unstable tail statistic from a handful of samples.
    if len(values) < 20:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return round(values[low] + (values[high] - values[low]) * (position - low), 2)


def calibrate(
    path=DEFAULT_FIXTURE,
    *,
    live=False,
    limit=40,
    provider=None,
    concurrency=4,
    timeout=10,
    fetch=public_get,
):
    if not 1 <= limit <= 40 or not 1 <= concurrency <= 4 or not 0 < timeout <= 30:
        raise ValueError("Probe bounds: limit 1–40, concurrency 1–4, timeout >0–30")
    rows = read_sources(path, limit, provider)
    unique = []
    indexes = []
    known = {}
    for row in rows:
        try:
            config = detect_source(row["url"], row["company"])
            key = (config.family, source_identity(config)) if config else ("url", row["url"])
        except ValueError:
            key = ("url", row["url"])
        if key not in known:
            known[key] = len(unique)
            unique.append(row)
        indexes.append(known[key])
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        unique_outcomes = list(
            executor.map(
                lambda row: _probe(
                    row, live=live, base=Path(path).parent, timeout=timeout, fetch=fetch
                ),
                unique,
            )
        )
    outcomes = []
    counted = set()
    for index in indexes:
        result, records = unique_outcomes[index]
        if index in counted:
            result = dict(
                result,
                status="DUPLICATE_SOURCE",
                jobs=0,
                records_examined=0,
                requests=0,
                unknown_pattern=None,
            )
            records = ()
        counted.add(index)
        outcomes.append((result, records))
    sources = [result for result, _ in outcomes]
    items = [(result["provider"], record) for result, records in outcomes for record in records]
    statuses = Counter(source["status"] for source in sources)
    identities = {(s["provider"], s["identity"]) for s in sources if s["identity"]}
    verified = {
        (s["provider"], s["identity"])
        for s in sources
        if s["status"] in {"SUCCESS", "VALID_EMPTY_SOURCE"}
    }
    candidates = []
    for _, record in items:
        for url in (record.source_url, record.application_url):
            try:
                config = detect_source(url, record.company)
                if config:
                    candidates.append((config.family, source_identity(config)))
            except ValueError:
                pass
    unknowns = Counter(
        (
            s["unknown_pattern"]["hostname"],
            s["unknown_pattern"]["url_structure"],
            s["unknown_pattern"]["probable_family"],
        )
        for s in sources
        if s["unknown_pattern"]
    )
    attempted = len(sources) - statuses["NOT_PROBED"] - statuses["DUPLICATE_SOURCE"]
    direct = sum(s["direct"] and s["status"] in {"SUCCESS", "VALID_EMPTY_SOURCE"} for s in sources)
    now = datetime.now(timezone.utc)
    return {
        "version": "coverage-v2",
        "mode": "live-read-only" if live else "offline-fixtures",
        "database_writes": 0,
        "sources_input": len(rows),
        "sources_probed": attempted,
        "sources_detected": sum(s["identity"] is not None for s in sources),
        "sources_supported": sum(s["provider"] is not None for s in sources),
        "sources_fetch_success": statuses["SUCCESS"],
        "sources_valid_empty": statuses["VALID_EMPTY_SOURCE"],
        "sources_fetch_failure": attempted
        - statuses["SUCCESS"]
        - statuses["VALID_EMPTY_SOURCE"]
        - statuses["UNSUPPORTED_PROVIDER"],
        "sources_unknown": statuses["UNSUPPORTED_PROVIDER"],
        "sources_not_probed": statuses["NOT_PROBED"],
        "duplicate_input_sources": statuses["DUPLICATE_SOURCE"],
        "jobs_observed": len(items),
        "records_examined": sum(s["records_examined"] for s in sources),
        "jobs_by_provider": dict(Counter(provider for provider, _ in items)),
        "sources_by_provider": dict(Counter(s["provider"] or "unknown" for s in sources)),
        "unique_source_identities": len(identities),
        "discovery_candidates": len(set(candidates)),
        "successful_discoveries": len(set(candidates) & verified),
        "duplicate_source_discoveries": len(candidates) - len(set(candidates)),
        "direct_source_count": direct,
        "direct_source_rate": round(direct / attempted, 4) if attempted else None,
        "field_completeness_by_provider": record_metrics(items, now),
        "unknown_providers": [
            dict(hostname=h, url_structure=p, probable_family=f, frequency=n, observed_jobs=None)
            for (h, p, f), n in unknowns.most_common()
        ],
        "error_categories": {
            k: v
            for k, v in statuses.items()
            if k not in {"SUCCESS", "VALID_EMPTY_SOURCE", "NOT_PROBED", "DUPLICATE_SOURCE"}
        },
        "student_inventory": dict(Counter(record.employment_type for _, record in items)),
        "career_levels": dict(Counter(record.career_level for _, record in items)),
        "role_inventory": dict(Counter(record.role for _, record in items)),
        "remote_scopes": dict(
            Counter(
                scope
                for _, record in items
                for location in record.locations
                if (scope := remote_scope(location))
            )
        ),
        "unique_apply_url_identities": len(
            {canonical_url_fingerprint(record.application_url) for _, record in items}
        ),
        "unique_canonical_jobs": None,
        "ingestion_lag": None,
        "verified_official_apply_rate": None,
        "metric_notes": [
            "At most five parsed jobs/source; this is a bounded sample, not total vacancies.",
            "Company comes from source configuration; generic publisher feeds do not establish hiring employer.",
            "Discovery success means a candidate identity also passed this bounded probe, not registration.",
            "Direct rate uses successful source authority, not independently verified Apply ownership.",
            "No writes: canonical deduplication and ingestion lag are not measured in probe mode.",
        ],
        "sources": sources,
    }
