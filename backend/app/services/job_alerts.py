"""Durable, deterministic private alerts for newly discovered canonical jobs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.models.base import utc_now
from backend.app.models.job import (
    JobAlert,
    JobAlertDeliveryState,
    JobLifecycle,
    NormalizedJob,
    SavedJobSearch,
    SavedSearchAlertMode,
)
from backend.app.repositories.job import JobRepository
from backend.app.repositories.job_alert import JobAlertRepository
from backend.app.schemas.job import (
    JobAlertInboxRead,
    JobAlertRead,
    JobAlertReadState,
    SavedSearchCriteria,
)
from backend.app.services.job import JobSearch, JobSearchValidationError

MAX_DELIVERY_ATTEMPTS = 3
RECONCILIATION_SLICE_SIZE = 250


@dataclass(frozen=True)
class AlertEvaluationOutcome:
    created: int
    scanned: int = 0


@dataclass(frozen=True)
class AlertDeliveryOutcome:
    delivered: int = 0
    suppressed: int = 0
    retried: int = 0
    failed: int = 0


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _scheduled_for(mode: str, now: datetime) -> datetime:
    """Return one deterministic UTC delivery boundary for a new event."""

    now = _utc(now)
    if mode == SavedSearchAlertMode.INSTANT:
        return now
    if mode == SavedSearchAlertMode.HOURLY_DIGEST:
        return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    if mode == SavedSearchAlertMode.DAILY_DIGEST:
        return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    raise ValueError("alert mode cannot be scheduled")


def _delivery_group_key(alert: JobAlert) -> tuple[object, ...]:
    """Digest jobs share one persisted delivery window; instant jobs stand alone."""

    if alert.delivery_mode == SavedSearchAlertMode.INSTANT:
        return (alert.id,)
    return (
        alert.user_id,
        alert.saved_search_id,
        alert.delivery_mode,
        alert.scheduled_for,
    )


class JobAlertService:
    """Evaluate canonical jobs with the Phase 22 query predicate, never a copy."""

    @staticmethod
    def _criteria(saved_search: SavedJobSearch) -> JobSearch | None:
        try:
            return JobSearch.from_saved_criteria(
                SavedSearchCriteria.model_validate(saved_search.criteria)
            )
        except (JobSearchValidationError, ValueError):
            # A manually corrupted legacy row is never permission to emit a
            # fabricated alert. Normal API writes validate before persistence.
            return None

    @classmethod
    def _evaluate_saved_search(
        cls,
        saved_search: SavedJobSearch,
        job: NormalizedJob,
        *,
        repository: JobAlertRepository,
        job_repository: JobRepository,
        now: datetime,
    ) -> bool:
        if repository.hidden_for_user(saved_search.user_id, job.id):
            return False
        criteria = cls._criteria(saved_search)
        if criteria is None or not job_repository.matches_active_job(job.id, criteria):
            return False
        return repository.add_alert_if_absent(
            user_id=saved_search.user_id,
            saved_search_id=saved_search.id,
            canonical_job_id=job.id,
            delivery_mode=saved_search.alert_mode,
            scheduled_for=_scheduled_for(saved_search.alert_mode, now),
            created_at=now,
        )

    @classmethod
    def evaluate_new_canonical_job(
        cls,
        job_id,
        session,
        now: datetime | None = None,
    ) -> AlertEvaluationOutcome:
        """Create durable events in the same transaction as a new canonical job."""

        now = _utc(now or utc_now())
        job = session.get(NormalizedJob, job_id)
        if (
            job is None
            or not job.is_active
            or job.lifecycle == JobLifecycle.CLOSED
        ):
            return AlertEvaluationOutcome(created=0)

        repository = JobAlertRepository(session)
        job_repository = JobRepository(session)
        created = sum(
            cls._evaluate_saved_search(
                saved_search,
                job,
                repository=repository,
                job_repository=job_repository,
                now=now,
            )
            for saved_search in repository.enabled_saved_searches_for_job(job.first_seen_at)
        )
        # Instant in-app availability is durable and transaction-safe. Digest
        # events remain pending until their deterministic scheduled window.
        AlertDeliveryService.deliver_due(session, now=now)
        session.flush()
        return AlertEvaluationOutcome(created=created)

    @classmethod
    def reconcile(
        cls,
        session,
        *,
        now: datetime | None = None,
        limit_per_search: int = RECONCILIATION_SLICE_SIZE,
    ) -> AlertEvaluationOutcome:
        """Bounded recovery for jobs after each saved search's durable cursor."""

        if not 1 <= limit_per_search <= 1_000:
            raise ValueError("limit_per_search must be between 1 and 1000")
        now = _utc(now or utc_now())
        repository = JobAlertRepository(session)
        job_repository = JobRepository(session)
        created = 0
        scanned = 0
        for saved_search in repository.enabled_saved_searches_for_reconciliation():
            jobs = repository.canonical_jobs_after_search_cursor(
                saved_search,
                now=now,
                limit=limit_per_search,
            )
            for job in jobs:
                scanned += 1
                created += cls._evaluate_saved_search(
                    saved_search,
                    job,
                    repository=repository,
                    job_repository=job_repository,
                    now=now,
                )
            if jobs:
                cursor = jobs[-1]
                saved_search.alert_evaluated_at = cursor.first_seen_at
                saved_search.alert_evaluated_job_id = cursor.id
                saved_search.updated_at = now
        session.flush()
        return AlertEvaluationOutcome(created=created, scanned=scanned)


class AlertDeliveryService:
    """Turn durable matching events into in-app availability with bounded retry."""

    @staticmethod
    def _retry_at(now: datetime, attempt_count: int) -> datetime:
        return now + timedelta(seconds=min(3_600, 60 * (2 ** max(0, attempt_count - 1))))

    @classmethod
    def deliver_due(
        cls,
        session,
        *,
        now: datetime | None = None,
        limit: int = 250,
        deliver_group: Callable[[tuple[JobAlert, ...]], None] | None = None,
    ) -> AlertDeliveryOutcome:
        if not 1 <= limit <= 1_000:
            raise ValueError("limit must be between 1 and 1000")
        now = _utc(now or utc_now())
        repository = JobAlertRepository(session)
        alerts = repository.due_alerts_for_update(now, limit=limit)
        visible_pairs = repository.visible_pairs_for_delivery(alerts)
        grouped: dict[tuple[object, ...], list[JobAlert]] = defaultdict(list)
        for alert in alerts:
            grouped[_delivery_group_key(alert)].append(alert)

        delivered = suppressed = retried = failed = 0
        for group in grouped.values():
            eligible = [
                alert
                for alert in group
                if (alert.user_id, alert.canonical_job_id) in visible_pairs
            ]
            eligible_ids = {alert.id for alert in eligible}
            for alert in group:
                if alert.id not in eligible_ids:
                    alert.delivery_state = JobAlertDeliveryState.SUPPRESSED
                    alert.next_retry_at = None
                    alert.last_error_code = None
                    alert.updated_at = now
                    suppressed += 1
            if not eligible:
                continue
            try:
                if deliver_group is not None:
                    deliver_group(tuple(eligible))
            except Exception:
                # The caller's implementation detail is deliberately not
                # persisted or exposed to users.
                for alert in eligible:
                    alert.attempt_count += 1
                    alert.updated_at = now
                    alert.last_error_code = "DELIVERY_FAILED"
                    if alert.attempt_count >= MAX_DELIVERY_ATTEMPTS:
                        alert.delivery_state = JobAlertDeliveryState.FAILED
                        alert.next_retry_at = None
                        failed += 1
                    else:
                        alert.delivery_state = JobAlertDeliveryState.PENDING
                        alert.next_retry_at = cls._retry_at(now, alert.attempt_count)
                        retried += 1
            else:
                for alert in eligible:
                    alert.delivery_state = JobAlertDeliveryState.DELIVERED
                    alert.delivered_at = now
                    alert.next_retry_at = None
                    alert.last_error_code = None
                    alert.updated_at = now
                    delivered += 1
        session.flush()
        return AlertDeliveryOutcome(
            delivered=delivered,
            suppressed=suppressed,
            retried=retried,
            failed=failed,
        )


class JobAlertInboxService:
    """Private alert-inbox reads and monotonic read-state changes."""

    @staticmethod
    def _read(row, locations: list[str]) -> JobAlertRead:
        payload = dict(row._mapping)
        payload["locations"] = locations
        return JobAlertRead(**payload)

    @classmethod
    def list(cls, user_id, uow) -> JobAlertInboxRead:
        repository = JobAlertRepository(uow.session)
        rows = repository.delivered_alert_rows(user_id)
        locations = repository.locations_for_jobs(
            {row.canonical_job_id for row in rows}
        )
        return JobAlertInboxRead(
            items=[
                cls._read(row, locations.get(row.canonical_job_id, []))
                for row in rows
            ],
            unread_count=repository.unread_count(user_id),
        )

    @classmethod
    def mark_read(cls, user_id, alert_id, uow) -> JobAlertReadState:
        repository = JobAlertRepository(uow.session)
        alert = repository.delivered_alert_for_update(user_id, alert_id)
        if alert is None:
            raise StudentSuccessfulException(404, "ALERT_NOT_FOUND", "Alert not found")
        alert.read_at = alert.read_at or utc_now()
        alert.updated_at = utc_now()
        uow.session.flush()
        result = JobAlertReadState(id=alert.id, read_at=alert.read_at)
        uow.commit()
        return result


__all__ = [
    "AlertDeliveryOutcome",
    "AlertDeliveryService",
    "AlertEvaluationOutcome",
    "JobAlertInboxService",
    "JobAlertService",
]
