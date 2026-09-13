"""Durable private new-job alert queries and concurrency-safe inserts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert

from backend.app.models.job import (
    JobAlert,
    JobAlertDeliveryState,
    JobLifecycle,
    JobLocation,
    NormalizedJob,
    SavedJobSearch,
    SavedSearchAlertMode,
    UserJobState,
)
from backend.app.models.taxonomy import Company


class JobAlertRepository:
    """Keep alert ownership, delivery, and worker internals out of public APIs."""

    def __init__(self, session):
        self.session = session

    def enabled_saved_searches_for_job(self, first_seen_at: datetime) -> tuple[SavedJobSearch, ...]:
        return tuple(
            self.session.scalars(
                select(SavedJobSearch)
                .where(
                    SavedJobSearch.alert_mode != SavedSearchAlertMode.OFF,
                    SavedJobSearch.alert_watermark_at.is_not(None),
                    SavedJobSearch.alert_watermark_at < first_seen_at,
                )
                .order_by(SavedJobSearch.user_id, SavedJobSearch.id)
            ).all()
        )

    def enabled_saved_searches_for_reconciliation(self) -> tuple[SavedJobSearch, ...]:
        return tuple(
            self.session.scalars(
                select(SavedJobSearch)
                .where(
                    SavedJobSearch.alert_mode != SavedSearchAlertMode.OFF,
                    SavedJobSearch.alert_watermark_at.is_not(None),
                )
                .order_by(SavedJobSearch.user_id, SavedJobSearch.id)
            ).all()
        )

    def canonical_jobs_after_search_cursor(
        self,
        saved_search: SavedJobSearch,
        *,
        now: datetime,
        limit: int,
    ) -> tuple[NormalizedJob, ...]:
        """Return one bounded ordered slice after this search's durable cursor."""

        assert saved_search.alert_watermark_at is not None
        cursor_at = saved_search.alert_evaluated_at or saved_search.alert_watermark_at
        cursor_id = saved_search.alert_evaluated_job_id
        after_cursor = NormalizedJob.first_seen_at > cursor_at
        if cursor_id is not None:
            after_cursor = or_(
                after_cursor,
                and_(
                    NormalizedJob.first_seen_at == cursor_at,
                    NormalizedJob.id > cursor_id,
                ),
            )
        return tuple(
            self.session.scalars(
                select(NormalizedJob)
                .where(
                    NormalizedJob.is_active.is_(True),
                    NormalizedJob.lifecycle != JobLifecycle.CLOSED,
                    NormalizedJob.first_seen_at > saved_search.alert_watermark_at,
                    NormalizedJob.first_seen_at <= now,
                    after_cursor,
                )
                .order_by(NormalizedJob.first_seen_at, NormalizedJob.id)
                .limit(limit)
            ).all()
        )

    def hidden_for_user(self, user_id: UUID, job_id: UUID) -> bool:
        return bool(
            self.session.scalar(
                select(UserJobState.hidden).where(
                    UserJobState.user_id == user_id,
                    UserJobState.canonical_job_id == job_id,
                )
            )
        )

    def add_alert_if_absent(
        self,
        *,
        user_id: UUID,
        saved_search_id: UUID,
        canonical_job_id: UUID,
        delivery_mode: str,
        scheduled_for: datetime,
        created_at: datetime,
    ) -> bool:
        """Use PostgreSQL's unique index as the final race-safe deduplication gate."""

        statement = (
            insert(JobAlert)
            .values(
                user_id=user_id,
                saved_search_id=saved_search_id,
                canonical_job_id=canonical_job_id,
                delivery_mode=delivery_mode,
                delivery_state=JobAlertDeliveryState.PENDING,
                scheduled_for=scheduled_for,
                created_at=created_at,
                updated_at=created_at,
            )
            .on_conflict_do_nothing(
                constraint="uq_job_alerts_owner_search_job",
            )
            .returning(JobAlert.id)
        )
        return self.session.scalar(statement) is not None

    def due_alerts_for_update(self, now: datetime, *, limit: int) -> tuple[JobAlert, ...]:
        return tuple(
            self.session.scalars(
                select(JobAlert)
                .where(
                    JobAlert.delivery_state == JobAlertDeliveryState.PENDING,
                    JobAlert.scheduled_for <= now,
                    or_(JobAlert.next_retry_at.is_(None), JobAlert.next_retry_at <= now),
                )
                .order_by(JobAlert.scheduled_for, JobAlert.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
        )

    def visible_pairs_for_delivery(self, alerts: tuple[JobAlert, ...]) -> set[tuple[UUID, UUID]]:
        """Bulk-check current lifecycle and private hidden state before delivery."""

        if not alerts:
            return set()
        job_ids = {alert.canonical_job_id for alert in alerts}
        user_ids = {alert.user_id for alert in alerts}
        active_job_ids = set(
            self.session.scalars(
                select(NormalizedJob.id).where(
                    NormalizedJob.id.in_(job_ids),
                    NormalizedJob.is_active.is_(True),
                    NormalizedJob.lifecycle != JobLifecycle.CLOSED,
                )
            ).all()
        )
        hidden_pairs = {
            (row["user_id"], row["canonical_job_id"])
            for row in self.session.execute(
                select(UserJobState.user_id, UserJobState.canonical_job_id).where(
                    UserJobState.user_id.in_(user_ids),
                    UserJobState.canonical_job_id.in_(job_ids),
                    UserJobState.hidden.is_(True),
                )
            ).mappings()
        }
        return {
            (alert.user_id, alert.canonical_job_id)
            for alert in alerts
            if alert.canonical_job_id in active_job_ids
            and (alert.user_id, alert.canonical_job_id) not in hidden_pairs
        }

    def delivered_alert_rows(self, user_id: UUID):
        return list(
            self.session.execute(
                select(
                    JobAlert.id,
                    JobAlert.canonical_job_id,
                    JobAlert.saved_search_id,
                    SavedJobSearch.name.label("saved_search_name"),
                    JobAlert.delivery_mode,
                    JobAlert.scheduled_for,
                    JobAlert.created_at,
                    JobAlert.delivered_at,
                    JobAlert.read_at,
                    NormalizedJob.title,
                    Company.name.label("company_name"),
                    NormalizedJob.employment_type,
                    NormalizedJob.work_mode,
                    NormalizedJob.application_url,
                    NormalizedJob.first_seen_at,
                )
                .join(SavedJobSearch, SavedJobSearch.id == JobAlert.saved_search_id)
                .join(NormalizedJob, NormalizedJob.id == JobAlert.canonical_job_id)
                .join(Company, Company.id == NormalizedJob.company_id)
                .where(
                    JobAlert.user_id == user_id,
                    JobAlert.delivery_state == JobAlertDeliveryState.DELIVERED,
                    JobAlert.delivered_at.is_not(None),
                )
                .order_by(JobAlert.delivered_at.desc(), JobAlert.id.desc())
            )
        )

    def locations_for_jobs(self, job_ids: set[UUID]) -> dict[UUID, list[str]]:
        if not job_ids:
            return {}
        locations: dict[UUID, list[str]] = {}
        for job_id, location_raw in self.session.execute(
            select(JobLocation.job_id, JobLocation.location_raw)
            .where(JobLocation.job_id.in_(job_ids))
            .order_by(JobLocation.job_id, JobLocation.location_raw, JobLocation.id)
        ):
            if location_raw is not None:
                locations.setdefault(job_id, []).append(location_raw)
        return locations

    def unread_count(self, user_id: UUID) -> int:
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(JobAlert)
                .where(
                    JobAlert.user_id == user_id,
                    JobAlert.delivery_state == JobAlertDeliveryState.DELIVERED,
                    JobAlert.read_at.is_(None),
                )
            )
            or 0
        )

    def delivered_alert_for_update(self, user_id: UUID, alert_id: UUID) -> JobAlert | None:
        return self.session.scalar(
            select(JobAlert)
            .where(
                JobAlert.id == alert_id,
                JobAlert.user_id == user_id,
                JobAlert.delivery_state == JobAlertDeliveryState.DELIVERED,
            )
            .with_for_update()
        )


__all__ = ["JobAlertRepository"]
