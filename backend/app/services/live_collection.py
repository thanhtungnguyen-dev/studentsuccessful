"""Bounded, durable scheduling for Phase 18 public live-job sources."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.ingestion.adapters import SourceAdapterRegistry
from backend.app.ingestion.live import (
    LiveJobSourceConfig,
    LiveSourceAdapter,
    LiveSourceFetchError,
    create_live_adapter,
)
from backend.app.models.base import utc_now
from backend.app.models.job import LiveSourceHealth, LiveSourceState
from backend.app.repositories.job_ingestion import JobIngestionRepository
from backend.app.repositories.live_collection import LiveSourceClaim, LiveSourceStateRepository
from backend.app.services.canonical_jobs import CanonicalJobService
from backend.app.services.job_ingestion import JobIngestionValidationError
from backend.app.services.live_job_ingestion import (
    LiveJobIngestionService,
    LiveSourceIngestionResult,
)

DEFAULT_POLL_INTERVAL_SECONDS = {
    "greenhouse": 900,
    "lever": 600,
    "ashby": 900,
    "smartrecruiters": 900,
    "rss": 1800,
}
INITIAL_BACKOFF_SECONDS = 60
MAX_RETRY_AFTER_SECONDS = 86_400


@dataclass(frozen=True)
class LiveCollectionOutcome:
    """The bounded result of one independently collected source."""

    source_key: str
    family: str
    result: LiveSourceIngestionResult | None
    error_category: str | None = None
    http_status: int | None = None
    retry_after_seconds: int | None = None

    @property
    def succeeded(self) -> bool:
        return self.result is not None


@dataclass(frozen=True)
class LiveCollectionCycle:
    """Completed source outcomes from one scheduler pass."""

    outcomes: tuple[LiveCollectionOutcome, ...]

    @property
    def attempted(self) -> int:
        return len(self.outcomes)

    @property
    def failed(self) -> int:
        return sum(not outcome.succeeded for outcome in self.outcomes)


@dataclass(frozen=True)
class LiveSourceHealthSnapshot:
    """Small operator-facing source health view with no provider payloads."""

    source_key: str
    family: str
    enabled: bool
    health: str
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_completed_at: datetime | None
    next_poll_at: datetime | None
    consecutive_failures: int
    last_error_category: str | None
    last_error_at: datetime | None
    last_http_status: int | None
    last_jobs_seen: int | None
    last_jobs_ingested: int | None
    total_collection_attempts: int
    total_collection_failures: int
    total_jobs_observed: int
    total_jobs_ingested: int
    total_new_canonical_jobs: int
    total_duplicate_contributions: int
    total_internship_or_coop_contributions: int
    total_official_apply_urls: int
    last_new_canonical_job_at: datetime | None


def deterministic_jitter_seconds(source_key: str, base_seconds: int, attempt: int = 0) -> int:
    """Return a stable per-source delay that avoids synchronized polling bursts."""

    cap = min(60, max(1, base_seconds // 10))
    payload = f"{source_key}:{base_seconds}:{attempt}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big") % (cap + 1)


def bounded_backoff_seconds(
    source_key: str,
    consecutive_failures: int,
    *,
    max_backoff_seconds: int,
    retry_after_seconds: int | None = None,
    jitter: Callable[[str, int, int], int] = deterministic_jitter_seconds,
) -> int:
    """Calculate deterministic exponential backoff and respect bounded Retry-After."""

    if consecutive_failures < 1:
        raise ValueError("consecutive_failures must be positive")
    if max_backoff_seconds < INITIAL_BACKOFF_SECONDS:
        raise ValueError("max_backoff_seconds is too small")
    exponent = min(consecutive_failures - 1, 16)
    base = min(INITIAL_BACKOFF_SECONDS * (2**exponent), max_backoff_seconds)
    delay = min(max_backoff_seconds, base + max(0, jitter(source_key, base, consecutive_failures)))
    if retry_after_seconds is not None and retry_after_seconds >= 0:
        delay = max(delay, min(int(retry_after_seconds), MAX_RETRY_AFTER_SECONDS))
    return delay


class LiveCollectionService:
    """Run configured public sources independently while persisting only health state."""

    def __init__(
        self,
        configs: Iterable[LiveJobSourceConfig],
        *,
        default_timeout_seconds: float,
        max_concurrency: int = 3,
        max_backoff_seconds: int = 3_600,
        uow_factory: Callable[[], UnitOfWork] = UnitOfWork,
        now: Callable[[], datetime] = utc_now,
        jitter: Callable[[str, int, int], int] = deterministic_jitter_seconds,
    ) -> None:
        self.configs = tuple(configs)
        self.default_timeout_seconds = default_timeout_seconds
        self.max_concurrency = max_concurrency
        self.max_backoff_seconds = max_backoff_seconds
        self._uow_factory = uow_factory
        self._now = now
        self._jitter = jitter
        if default_timeout_seconds <= 0:
            raise ValueError("default_timeout_seconds must be positive")
        if not 1 <= max_concurrency <= 16:
            raise ValueError("max_concurrency must be between 1 and 16")
        if not INITIAL_BACKOFF_SECONDS <= max_backoff_seconds <= MAX_RETRY_AFTER_SECONDS:
            raise ValueError("max_backoff_seconds must be between 60 and 86400")

    def normal_poll_interval_seconds(self, config: LiveJobSourceConfig) -> int:
        if config.poll_interval_seconds is not None:
            return config.poll_interval_seconds
        base = DEFAULT_POLL_INTERVAL_SECONDS[config.family]
        # Operators choose this explicit, inspectable tier from persisted source
        # metrics. It is intentionally not a hidden ranking model.
        if config.polling_tier == "high":
            return max(300, base // 2)
        if config.polling_tier == "low":
            return min(86_400, base * 2)
        return base

    def request_timeout_seconds(self, config: LiveJobSourceConfig) -> float:
        return config.request_timeout_seconds or self.default_timeout_seconds

    def synchronize(self, now: datetime | None = None) -> None:
        now = self._utc(now or self._now())
        intervals = {config.key: self.normal_poll_interval_seconds(config) for config in self.configs}
        with self._uow_factory() as uow:
            repository = LiveSourceStateRepository(uow.session)
            repository.synchronize_configurations(self.configs, intervals, now)
            repository.mark_stale((config.key for config in self.configs), now)
            uow.commit()

    def run_cycle(self, *, force: bool = False) -> LiveCollectionCycle:
        """Claim due sources, run them with bounded concurrency, and persist outcomes."""

        now = self._utc(self._now())
        self.synchronize(now)
        claims = self._claim_due(now, force=force)
        if not claims:
            return LiveCollectionCycle(())

        adapters = tuple(
            create_live_adapter(
                claim.config, timeout_seconds=self.request_timeout_seconds(claim.config)
            )
            for claim in claims
        )
        registry = SourceAdapterRegistry(adapters)
        outcomes: list[LiveCollectionOutcome] = []
        if self.max_concurrency == 1:
            completed = ((claim, self._outcome_for_claim(claim, registry)) for claim in claims)
            for claim, outcome in completed:
                self._record_outcome(claim, outcome, self._utc(self._now()))
                outcomes.append(outcome)
        else:
            with ThreadPoolExecutor(
                max_workers=min(self.max_concurrency, len(claims)),
                thread_name_prefix="live-source",
            ) as executor:
                futures = {
                    executor.submit(self._outcome_for_claim, claim, registry): claim
                    for claim in claims
                }
                for future in as_completed(futures):
                    claim = futures[future]
                    outcome = future.result()
                    self._record_outcome(claim, outcome, self._utc(self._now()))
                    outcomes.append(outcome)
        return LiveCollectionCycle(tuple(sorted(outcomes, key=lambda outcome: outcome.source_key)))

    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        """Keep collecting until SIGINT/SIGTERM sets the supplied event."""

        stop_event = stop_event or threading.Event()
        while not stop_event.is_set():
            self.run_cycle(force=False)
            stop_event.wait(self.seconds_until_next_poll())

    def seconds_until_next_poll(self) -> int:
        now = self._utc(self._now())
        snapshots = self.health_snapshots()
        upcoming = [
            snapshot.next_poll_at
            for snapshot in snapshots
            if snapshot.enabled and snapshot.next_poll_at is not None
        ]
        if not upcoming:
            return 60
        delay = min((value - now).total_seconds() for value in upcoming)
        return max(1, min(60, int(delay) if delay > 0 else 1))

    def health_snapshots(self) -> tuple[LiveSourceHealthSnapshot, ...]:
        with self._uow_factory() as uow:
            states = LiveSourceStateRepository(uow.session).list_states()
            return tuple(self._snapshot(state) for state in states)

    def _claim_due(self, now: datetime, *, force: bool) -> tuple[LiveSourceClaim, ...]:
        longest_timeout = max(
            (self.request_timeout_seconds(config) for config in self.configs if config.enabled),
            default=self.default_timeout_seconds,
        )
        # A lease outlives one request but expires quickly after a crashed worker.
        lease_seconds = max(60, int(longest_timeout) + 60)
        with self._uow_factory() as uow:
            claims = LiveSourceStateRepository(uow.session).claim_due(
                self.configs, now, force=force, lease_seconds=lease_seconds
            )
            uow.commit()
            return claims

    def _collect_claim(
        self, claim: LiveSourceClaim, registry: SourceAdapterRegistry
    ) -> LiveCollectionOutcome:
        adapter = registry.resolve(claim.config.key)
        if not isinstance(adapter, LiveSourceAdapter):
            raise ValueError("configured collector adapter is invalid")
        fetched = adapter.fetch_with_metadata(etag=claim.etag, last_modified=claim.last_modified)
        result = LiveJobIngestionService.ingest_adapter(adapter, registry, fetch_result=fetched)
        return LiveCollectionOutcome(
            source_key=claim.config.key,
            family=claim.config.family,
            result=result,
            http_status=result.http_status,
        )

    def _outcome_for_claim(
        self, claim: LiveSourceClaim, registry: SourceAdapterRegistry
    ) -> LiveCollectionOutcome:
        try:
            return self._collect_claim(claim, registry)
        except LiveSourceFetchError as exc:
            return LiveCollectionOutcome(
                source_key=claim.config.key,
                family=claim.config.family,
                result=None,
                error_category=exc.category,
                http_status=exc.status_code,
                retry_after_seconds=exc.retry_after_seconds,
            )
        except (JobIngestionValidationError, ValueError):
            return LiveCollectionOutcome(
                source_key=claim.config.key,
                family=claim.config.family,
                result=None,
                error_category="INGESTION",
            )
        except Exception:
            # External data and transport errors never disclose raw provider text to storage.
            return LiveCollectionOutcome(
                source_key=claim.config.key,
                family=claim.config.family,
                result=None,
                error_category="UNEXPECTED",
            )

    def _record_outcome(
        self,
        claim: LiveSourceClaim,
        outcome: LiveCollectionOutcome,
        completed_at: datetime,
    ) -> None:
        with self._uow_factory() as uow:
            state = LiveSourceStateRepository(uow.session).claimed_state(
                claim.config.key, claim.token
            )
            if state is not None:
                if outcome.succeeded:
                    assert outcome.result is not None
                    self._apply_success(state, outcome.result, completed_at)
                    if self._safe_for_lifecycle_reconciliation(outcome.result):
                        CanonicalJobService.record_successful_source_refresh(
                            claim.config.key,
                            outcome.result.observed_external_ids,
                            JobIngestionRepository(uow.session),
                            uow.session,
                            completed_at,
                        )
                else:
                    self._apply_failure(state, outcome, completed_at)
            uow.commit()

    def _apply_success(
        self,
        state: LiveSourceState,
        result: LiveSourceIngestionResult,
        completed_at: datetime,
    ) -> None:
        prior_seen = state.last_jobs_seen
        state.total_collection_attempts += 1
        state.total_jobs_observed += result.parsed
        state.total_jobs_ingested += result.ingested
        state.total_new_canonical_jobs += result.new_canonical_jobs
        state.total_duplicate_contributions += result.duplicate_contributions
        state.total_internship_or_coop_contributions += result.internship_or_coop_contributions
        state.total_official_apply_urls += result.official_apply_urls
        if result.new_canonical_jobs:
            state.last_new_canonical_job_at = completed_at
        state.last_success_at = completed_at
        state.last_completed_at = completed_at
        state.consecutive_failures = 0
        state.last_error_category = None
        state.last_error_at = None
        state.last_http_status = result.http_status
        state.last_jobs_ingested = result.ingested
        if result.not_modified:
            state.consecutive_empty_successes = 0
        else:
            state.last_jobs_seen = result.parsed
            examined = result.fetched - result.filtered
            all_examined_rejected = (
                examined > 0
                and result.parsed == 0
                and result.malformed + result.rejected >= examined
            )
            suspicious_empty = result.parsed == 0 and (
                (prior_seen or 0) > 0
                or state.consecutive_empty_successes > 0
                or all_examined_rejected
            )
            if suspicious_empty:
                state.consecutive_empty_successes += 1
            else:
                state.consecutive_empty_successes = 0
        if result.not_modified or result.parsed > 0 or state.consecutive_empty_successes == 0:
            state.health = LiveSourceHealth.HEALTHY
        else:
            state.health = LiveSourceHealth.DEGRADED
        if not result.not_modified:
            state.etag = result.etag
            state.last_modified = result.last_modified
        else:
            if result.etag is not None:
                state.etag = result.etag
            if result.last_modified is not None:
                state.last_modified = result.last_modified
        interval = state.normal_poll_interval_seconds
        state.next_poll_at = completed_at + timedelta(
            seconds=interval + self._jitter_delay(state.source_key, interval, 0)
        )
        state.lease_token = None
        state.lease_expires_at = None
        state.updated_at = completed_at

    def _apply_failure(
        self,
        state: LiveSourceState,
        outcome: LiveCollectionOutcome,
        completed_at: datetime,
    ) -> None:
        state.last_completed_at = completed_at
        state.total_collection_attempts += 1
        state.total_collection_failures += 1
        state.consecutive_failures += 1
        state.last_error_category = outcome.error_category or "UNEXPECTED"
        state.last_error_at = completed_at
        state.last_http_status = outcome.http_status
        state.health = (
            LiveSourceHealth.RATE_LIMITED
            if outcome.error_category == "RATE_LIMITED"
            else LiveSourceHealth.FAILING
        )
        delay = bounded_backoff_seconds(
            state.source_key,
            state.consecutive_failures,
            max_backoff_seconds=self.max_backoff_seconds,
            retry_after_seconds=outcome.retry_after_seconds,
            jitter=self._jitter,
        )
        state.next_poll_at = completed_at + timedelta(seconds=delay)
        state.lease_token = None
        state.lease_expires_at = None
        state.updated_at = completed_at

    def _jitter_delay(self, source_key: str, base_seconds: int, attempt: int) -> int:
        cap = min(60, max(1, base_seconds // 10))
        return min(cap, max(0, int(self._jitter(source_key, base_seconds, attempt))))

    @staticmethod
    def _safe_for_lifecycle_reconciliation(result: LiveSourceIngestionResult) -> bool:
        """Only a complete, clean source listing is absence evidence."""

        return (
            result.complete_listing
            and not result.not_modified
            and result.malformed == 0
            and result.rejected == 0
            and result.filtered == 0
            and result.ingested == result.parsed
        )

    @staticmethod
    def _snapshot(state: LiveSourceState) -> LiveSourceHealthSnapshot:
        return LiveSourceHealthSnapshot(
            source_key=state.source_key,
            family=state.source_family,
            enabled=state.enabled,
            health=state.health,
            last_attempt_at=state.last_attempt_at,
            last_success_at=state.last_success_at,
            last_completed_at=state.last_completed_at,
            next_poll_at=state.next_poll_at,
            consecutive_failures=state.consecutive_failures,
            last_error_category=state.last_error_category,
            last_error_at=state.last_error_at,
            last_http_status=state.last_http_status,
            last_jobs_seen=state.last_jobs_seen,
            last_jobs_ingested=state.last_jobs_ingested,
            total_collection_attempts=state.total_collection_attempts,
            total_collection_failures=state.total_collection_failures,
            total_jobs_observed=state.total_jobs_observed,
            total_jobs_ingested=state.total_jobs_ingested,
            total_new_canonical_jobs=state.total_new_canonical_jobs,
            total_duplicate_contributions=state.total_duplicate_contributions,
            total_internship_or_coop_contributions=state.total_internship_or_coop_contributions,
            total_official_apply_urls=state.total_official_apply_urls,
            last_new_canonical_job_at=state.last_new_canonical_job_at,
        )

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("collector clock must return an aware timestamp")
        return value.astimezone(timezone.utc)


__all__ = [
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "LiveCollectionCycle",
    "LiveCollectionOutcome",
    "LiveCollectionService",
    "LiveSourceHealthSnapshot",
    "bounded_backoff_seconds",
    "deterministic_jitter_seconds",
]
