"""Focused Phase 23 durable canonical-job alert behavior."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.ingestion.adapters import SourceAdapterRegistry
from backend.app.ingestion.dto import ExternalJobDTO
from backend.app.main import app
from backend.app.models.job import (
    JobAlert,
    JobAlertDeliveryState,
    JobLifecycle,
    JobLocation,
    JobSourceObservation,
    JobSourceRecord,
    NormalizedJob,
    SavedJobSearch,
    SavedSearchAlertMode,
)
from backend.app.models.taxonomy import Company, Location, Role
from backend.app.models.user import User
from backend.app.repositories.job_alert import JobAlertRepository
from backend.app.services.job_alerts import AlertDeliveryService, JobAlertService
from backend.app.services.job_ingestion import JobIngestionService

ALERTS_URL = "/api/v1/alerts"
JOBS_URL = "/api/v1/jobs"
SAVED_SEARCHES_URL = "/api/v1/saved-searches"


@dataclass
class FixtureAdapter:
    key: str
    source_authority: str = "TRUSTED_STRUCTURED"

    def fetch(self):
        return ()


def ingestion_registry(adapter_key: str) -> SourceAdapterRegistry:
    return SourceAdapterRegistry([FixtureAdapter(adapter_key)])


def account() -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"phase23-{uuid4().hex}@example.com", "password": "Phase23-password-123!"},
    )
    assert response.status_code == 201, response.text
    return client


def csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["ss_csrf"]}


def user_id(client: TestClient) -> UUID:
    return UUID(client.get("/api/v1/auth/me").json()["id"])


def seed_job(
    connection,
    *,
    title: str,
    external_id: str,
    first_seen_at: datetime,
    role_slug: str,
    role_id: UUID | None = None,
    country: str | None = "CA",
    region: str | None = "Ontario",
    city: str | None = "Toronto",
    employment_type: str = "INTERNSHIP",
    work_mode: str = "HYBRID",
    lifecycle: str = JobLifecycle.ACTIVE,
    is_active: bool = True,
):
    company_id, source_id, job_id = uuid4(), uuid4(), uuid4()
    connection.execute(
        Company.__table__.insert(),
        {"id": company_id, "name": f"{title} Company", "is_verified": True},
    )
    if role_id is None:
        role_id = uuid4()
        connection.execute(
            Role.__table__.insert(),
            {
                "id": role_id,
                "name": role_slug.replace("-", " ").title(),
                "slug": role_slug,
                "is_active": True,
            },
        )
    connection.execute(
        JobSourceRecord.__table__.insert(),
        {
            "id": source_id,
            "source_adapter": "greenhouse",
            "external_id": external_id,
            "source_url": f"https://source.example/{external_id}",
        },
    )
    connection.execute(
        NormalizedJob.__table__.insert(),
        {
            "id": job_id,
            "job_source_record_id": source_id,
            "company_id": company_id,
            "title": title,
            "description": f"{title} API platform description",
            "role_id": role_id,
            "employment_type": employment_type,
            "career_level": "STUDENT",
            "work_mode": work_mode,
            "application_url": f"https://apply.example/{external_id}",
            "is_active": is_active,
            "lifecycle": lifecycle,
            "first_seen_at": first_seen_at,
            "last_seen_at": first_seen_at,
            "last_verified_at": first_seen_at,
            "canonical_updated_at": first_seen_at,
            "discovered_at": first_seen_at,
        },
    )
    if country is not None:
        location_id = uuid4()
        connection.execute(
            Location.__table__.insert(),
            {
                "id": location_id,
                "country_code": country,
                "state_province": region,
                "city": city or "Unknown",
            },
        )
        connection.execute(
            JobLocation.__table__.insert(),
            {
                "id": uuid4(),
                "job_id": job_id,
                "location_id": location_id,
                "location_raw": ", ".join(
                    part for part in (city, region, country) if part
                ),
            },
        )
    return job_id, company_id, role_id, source_id


def add_source_observation(
    connection,
    *,
    job_id: UUID,
    company_id: UUID,
    role_id: UUID,
    external_id: str,
) -> None:
    source_id = uuid4()
    connection.execute(
        JobSourceRecord.__table__.insert(),
        {
            "id": source_id,
            "source_adapter": "lever",
            "external_id": external_id,
            "source_url": f"https://source.example/{external_id}",
        },
    )
    connection.execute(
        JobSourceObservation.__table__.insert(),
        {
            "id": uuid4(),
            "canonical_job_id": job_id,
            "job_source_record_id": source_id,
            "source_authority": "OFFICIAL_ATS",
            "source_url": f"https://source.example/{external_id}",
            "application_url": f"https://apply.example/{external_id}",
            "source_url_fingerprint": "a" * 64,
            "application_url_fingerprint": "b" * 64,
            "company_id": company_id,
            "role_id": role_id,
            "title": "Duplicate source observation",
            "description": "Another source reporting the same canonical job",
            "employment_type": "INTERNSHIP",
            "career_level": "STUDENT",
            "work_mode": "HYBRID",
        },
    )


def create_saved_search(
    client: TestClient,
    connection,
    *,
    name: str,
    role_slug: str,
    mode: str = SavedSearchAlertMode.INSTANT,
    watermark: datetime | None = None,
    countries: list[str] | None = None,
    recency: str = "all",
    keyword: str | None = None,
) -> dict:
    response = client.post(
        SAVED_SEARCHES_URL,
        json={
            "name": name,
            "criteria": {
                "roles": [role_slug],
                "countries": countries or [],
                "job_types": ["INTERNSHIP"],
                "work_modes": ["HYBRID"],
                "recency": recency,
                "keyword": keyword,
            },
            "alert_mode": mode,
        },
        headers=csrf(client),
    )
    assert response.status_code == 201, response.text
    saved = response.json()
    if mode != SavedSearchAlertMode.OFF and watermark is not None:
        connection.execute(
            update(SavedJobSearch)
            .where(SavedJobSearch.id == UUID(saved["id"]))
            .values(
                alert_enabled_at=watermark,
                alert_watermark_at=watermark,
                alert_evaluated_at=watermark,
                alert_evaluated_job_id=None,
            )
        )
    return saved


def evaluate(connection, job_id: UUID, now: datetime):
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        outcome = JobAlertService.evaluate_new_canonical_job(job_id, session, now=now)
        session.commit()
        return outcome
    finally:
        session.close()


def reconcile(connection, now: datetime):
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        outcome = JobAlertService.reconcile(session, now=now)
        session.commit()
        return outcome
    finally:
        session.close()


def deliver(connection, now: datetime, deliver_group=None):
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        outcome = AlertDeliveryService.deliver_due(
            session,
            now=now,
            deliver_group=deliver_group,
        )
        session.commit()
        return outcome
    finally:
        session.close()


def alert_rows(connection) -> list[JobAlert]:
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        return list(session.scalars(select(JobAlert).order_by(JobAlert.created_at, JobAlert.id)))
    finally:
        session.close()


def test_matching_new_canonical_job_is_delivered_once_with_phase22_filter_semantics(
    isolated_database,
):
    client, other = account(), account()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    role_slug = "backend-phase23-matching"
    saved = create_saved_search(
        client,
        isolated_database,
        name="Canada API internships",
        role_slug=role_slug,
        countries=["CA"],
        recency="24h",
        keyword="API",
        watermark=now - timedelta(hours=2),
    )
    other_saved = create_saved_search(
        other,
        isolated_database,
        name="Other Canada API internships",
        role_slug=role_slug,
        countries=["CA"],
        recency="24h",
        keyword="API",
        watermark=now - timedelta(hours=2),
    )
    job_id, company_id, role_id, _ = seed_job(
        isolated_database,
        title="Backend API Internship",
        external_id="matching",
        first_seen_at=now - timedelta(minutes=5),
        role_slug=role_slug,
    )
    visible = client.get(
        JOBS_URL,
        params={
            "role": role_slug,
            "country": "CA",
            "job_type": "INTERNSHIP",
            "work_mode": "HYBRID",
            "keyword": "API",
            "recency": "24h",
        },
    )
    assert visible.status_code == 200
    assert [item["id"] for item in visible.json()["items"]] == [str(job_id)]

    assert evaluate(isolated_database, job_id, now).created == 2
    assert evaluate(isolated_database, job_id, now + timedelta(minutes=1)).created == 0
    add_source_observation(
        isolated_database,
        job_id=job_id,
        company_id=company_id,
        role_id=role_id,
        external_id="matching-duplicate-source",
    )
    assert evaluate(isolated_database, job_id, now + timedelta(minutes=2)).created == 0

    rows = alert_rows(isolated_database)
    assert len(rows) == 2
    assert {row.saved_search_id for row in rows} == {
        UUID(saved["id"]),
        UUID(other_saved["id"]),
    }
    assert {row.delivery_state for row in rows} == {JobAlertDeliveryState.DELIVERED}
    assert {row.delivery_mode for row in rows} == {SavedSearchAlertMode.INSTANT}
    assert evaluate(isolated_database, job_id, now + timedelta(days=2)).created == 0
    assert len(alert_rows(isolated_database)) == 2


def test_off_historical_and_changed_saved_searches_never_backfill(
    isolated_database,
):
    client = account()
    role_slug = "backend-phase23-history"
    old = datetime.now(timezone.utc) - timedelta(days=2)
    historical_job, _, historical_role_id, _ = seed_job(
        isolated_database,
        title="Historical Backend Internship",
        external_id="historical",
        first_seen_at=old,
        role_slug=role_slug,
    )
    saved = create_saved_search(
        client,
        isolated_database,
        name="History safe search",
        role_slug=role_slug,
        mode=SavedSearchAlertMode.OFF,
    )
    assert evaluate(isolated_database, historical_job, datetime.now(timezone.utc)).created == 0

    enabled = client.patch(
        SAVED_SEARCHES_URL + "/" + saved["id"],
        json={"alert_mode": SavedSearchAlertMode.INSTANT},
        headers=csrf(client),
    )
    assert enabled.status_code == 200
    assert enabled.json()["alert_enabled_at"] is not None
    assert evaluate(isolated_database, historical_job, datetime.now(timezone.utc)).created == 0

    pre_update_job, *_ = seed_job(
        isolated_database,
        title="Backend API Internship Before Criteria Change",
        external_id="criteria-before-change",
        first_seen_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        role_slug=role_slug,
        role_id=historical_role_id,
    )
    changed = client.patch(
        SAVED_SEARCHES_URL + "/" + saved["id"],
        json={
            "criteria": {
                "roles": [role_slug],
                "countries": ["CA"],
                "job_types": ["INTERNSHIP"],
                "work_modes": ["HYBRID"],
                "recency": "all",
                "keyword": "API",
            }
        },
        headers=csrf(client),
    )
    assert changed.status_code == 200
    assert changed.json()["alert_enabled_at"] is not None
    recovery = reconcile(isolated_database, datetime.now(timezone.utc) + timedelta(minutes=1))
    assert recovery.created == 0
    assert not alert_rows(isolated_database)
    assert evaluate(isolated_database, pre_update_job, datetime.now(timezone.utc)).created == 0


def test_reenabling_establishes_a_new_boundary_then_allows_future_jobs(
    isolated_database,
):
    client = account()
    role_slug = "backend-phase23-reenable"
    saved = create_saved_search(
        client,
        isolated_database,
        name="Re-enable safely",
        role_slug=role_slug,
        watermark=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    disabled = client.patch(
        SAVED_SEARCHES_URL + "/" + saved["id"],
        json={"alert_mode": SavedSearchAlertMode.OFF},
        headers=csrf(client),
    )
    assert disabled.status_code == 200
    assert disabled.json()["alert_enabled_at"] is None
    disabled_job, _, disabled_role_id, _ = seed_job(
        isolated_database,
        title="Disabled Interval Internship",
        external_id="disabled-interval",
        first_seen_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        role_slug=role_slug,
    )
    assert evaluate(isolated_database, disabled_job, datetime.now(timezone.utc)).created == 0

    enabled = client.patch(
        SAVED_SEARCHES_URL + "/" + saved["id"],
        json={"alert_mode": SavedSearchAlertMode.INSTANT},
        headers=csrf(client),
    )
    assert enabled.status_code == 200
    watermark = isolated_database.execute(
        select(SavedJobSearch.alert_watermark_at).where(
            SavedJobSearch.id == UUID(saved["id"])
        )
    ).scalar_one()
    assert evaluate(isolated_database, disabled_job, watermark + timedelta(minutes=1)).created == 0

    future_job, *_ = seed_job(
        isolated_database,
        title="Future Backend Internship",
        external_id="future-after-reenable",
        first_seen_at=watermark + timedelta(seconds=1),
        role_slug=role_slug,
        role_id=disabled_role_id,
    )
    assert evaluate(isolated_database, future_job, watermark + timedelta(seconds=2)).created == 1
    assert [row.canonical_job_id for row in alert_rows(isolated_database)] == [future_job]


def test_closed_and_hidden_jobs_are_suppressed_per_owner(isolated_database):
    owner, other = account(), account()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    role_slug = "backend-phase23-privacy"
    for client, name in ((owner, "Owner search"), (other, "Other search")):
        create_saved_search(
            client,
            isolated_database,
            name=name,
            role_slug=role_slug,
            watermark=now - timedelta(hours=1),
        )
    closed_job, _, closed_role_id, _ = seed_job(
        isolated_database,
        title="Closed Backend Internship",
        external_id="closed",
        first_seen_at=now,
        role_slug=role_slug,
        lifecycle=JobLifecycle.CLOSED,
        is_active=False,
    )
    assert evaluate(isolated_database, closed_job, now).created == 0

    active_job, *_ = seed_job(
        isolated_database,
        title="Private Hidden Backend Internship",
        external_id="owner-hidden",
        first_seen_at=now + timedelta(seconds=1),
        role_slug=role_slug,
        role_id=closed_role_id,
    )
    hidden = owner.patch(
        JOBS_URL + "/" + str(active_job) + "/state",
        json={"hidden": True},
        headers=csrf(owner),
    )
    assert hidden.status_code == 200
    assert evaluate(isolated_database, active_job, now + timedelta(seconds=2)).created == 1
    rows = alert_rows(isolated_database)
    assert len(rows) == 1
    assert rows[0].user_id == user_id(other)
    assert rows[0].canonical_job_id == active_job
    assert rows[0].delivery_state == JobAlertDeliveryState.DELIVERED


def test_hourly_and_daily_digests_have_deterministic_grouped_delivery(
    isolated_database,
):
    client = account()
    now = datetime(2026, 9, 11, 10, 15, tzinfo=timezone.utc)
    hourly_role = "backend-phase23-hourly"
    hourly = create_saved_search(
        client,
        isolated_database,
        name="Hourly backend internships",
        role_slug=hourly_role,
        mode=SavedSearchAlertMode.HOURLY_DIGEST,
        watermark=now - timedelta(hours=1),
    )
    assert hourly["alert_mode"] == SavedSearchAlertMode.HOURLY_DIGEST
    first, _, role_id, _ = seed_job(
        isolated_database,
        title="Hourly First Internship",
        external_id="hourly-first",
        first_seen_at=now,
        role_slug=hourly_role,
    )
    second, *_ = seed_job(
        isolated_database,
        title="Hourly Second Internship",
        external_id="hourly-second",
        first_seen_at=now + timedelta(minutes=1),
        role_slug=hourly_role,
        role_id=role_id,
    )
    assert evaluate(isolated_database, first, now).created == 1
    assert evaluate(isolated_database, second, now + timedelta(minutes=1)).created == 1
    hourly_rows = [
        row for row in alert_rows(isolated_database) if row.saved_search_id == UUID(hourly["id"])
    ]
    assert len(hourly_rows) == 2
    assert {row.scheduled_for for row in hourly_rows} == {
        datetime(2026, 9, 11, 11, tzinfo=timezone.utc)
    }
    delivered_groups: list[tuple[JobAlert, ...]] = []
    result = deliver(
        isolated_database,
        datetime(2026, 9, 11, 11, tzinfo=timezone.utc),
        deliver_group=lambda group: delivered_groups.append(group),
    )
    assert result.delivered == 2
    assert [len(group) for group in delivered_groups] == [2]

    daily_role = "backend-phase23-daily"
    daily = create_saved_search(
        client,
        isolated_database,
        name="Daily backend internships",
        role_slug=daily_role,
        mode=SavedSearchAlertMode.DAILY_DIGEST,
        watermark=now - timedelta(hours=1),
    )
    assert daily["alert_mode"] == SavedSearchAlertMode.DAILY_DIGEST
    daily_job, *_ = seed_job(
        isolated_database,
        title="Daily Internship",
        external_id="daily",
        first_seen_at=now + timedelta(minutes=2),
        role_slug=daily_role,
    )
    assert evaluate(isolated_database, daily_job, now + timedelta(minutes=2)).created == 1
    daily_row = next(
        row for row in alert_rows(isolated_database) if row.saved_search_id == UUID(daily["id"])
    )
    assert daily_row.scheduled_for == datetime(2026, 9, 12, tzinfo=timezone.utc)
    assert deliver(isolated_database, daily_row.scheduled_for).delivered == 1


def test_queued_digest_is_suppressed_when_hidden_or_closed_before_delivery(
    isolated_database,
):
    client = account()
    now = datetime(2026, 9, 11, 10, 15, tzinfo=timezone.utc)
    role_slug = "backend-phase23-suppress"
    create_saved_search(
        client,
        isolated_database,
        name="Suppressed digest",
        role_slug=role_slug,
        mode=SavedSearchAlertMode.HOURLY_DIGEST,
        watermark=now - timedelta(hours=1),
    )
    hidden_job, _, role_id, _ = seed_job(
        isolated_database,
        title="Hidden before digest",
        external_id="hidden-digest",
        first_seen_at=now,
        role_slug=role_slug,
    )
    closed_job, *_ = seed_job(
        isolated_database,
        title="Closed before digest",
        external_id="closed-digest",
        first_seen_at=now + timedelta(minutes=1),
        role_slug=role_slug,
        role_id=role_id,
    )
    assert evaluate(isolated_database, hidden_job, now).created == 1
    assert evaluate(isolated_database, closed_job, now + timedelta(minutes=1)).created == 1
    assert client.patch(
        JOBS_URL + "/" + str(hidden_job) + "/state",
        json={"hidden": True},
        headers=csrf(client),
    ).status_code == 200
    isolated_database.execute(
        update(NormalizedJob)
        .where(NormalizedJob.id == closed_job)
        .values(is_active=False, lifecycle=JobLifecycle.CLOSED)
    )
    outcome = deliver(isolated_database, datetime(2026, 9, 11, 11, tzinfo=timezone.utc))
    assert outcome.suppressed == 2
    assert {row.delivery_state for row in alert_rows(isolated_database)} == {
        JobAlertDeliveryState.SUPPRESSED
    }
    assert client.get(ALERTS_URL).json() == {"items": [], "unread_count": 0}


def test_delivery_retries_are_bounded_and_delivered_events_do_not_replay(
    isolated_database,
):
    client = account()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    role_slug = "backend-phase23-retry"
    saved = create_saved_search(
        client,
        isolated_database,
        name="Retry search",
        role_slug=role_slug,
        watermark=now - timedelta(hours=1),
    )
    retry_job, _, retry_role_id, _ = seed_job(
        isolated_database,
        title="Retry Internship",
        external_id="retry",
        first_seen_at=now,
        role_slug=role_slug,
    )
    session = Session(bind=isolated_database, join_transaction_mode="create_savepoint")
    try:
        assert JobAlertRepository(session).add_alert_if_absent(
            user_id=user_id(client),
            saved_search_id=UUID(saved["id"]),
            canonical_job_id=retry_job,
            delivery_mode=SavedSearchAlertMode.INSTANT,
            scheduled_for=now,
            created_at=now,
        )
        session.commit()
    finally:
        session.close()

    def unavailable(_group) -> None:
        raise RuntimeError("delivery unavailable")

    first = deliver(isolated_database, now, deliver_group=unavailable)
    assert first.retried == 1
    row = alert_rows(isolated_database)[0]
    assert row.attempt_count == 1
    assert row.next_retry_at is not None
    second = deliver(isolated_database, row.next_retry_at, deliver_group=unavailable)
    assert second.retried == 1
    row = alert_rows(isolated_database)[0]
    third = deliver(isolated_database, row.next_retry_at, deliver_group=unavailable)
    assert third.failed == 1
    row = alert_rows(isolated_database)[0]
    assert row.delivery_state == JobAlertDeliveryState.FAILED
    assert row.attempt_count == 3
    assert row.next_retry_at is None
    assert deliver(isolated_database, now + timedelta(days=1)).delivered == 0

    delivered_job, *_ = seed_job(
        isolated_database,
        title="Delivered once Internship",
        external_id="delivered-once",
        first_seen_at=now + timedelta(minutes=1),
        role_slug=role_slug,
        role_id=retry_role_id,
    )
    assert evaluate(isolated_database, delivered_job, now + timedelta(minutes=2)).created == 1
    assert deliver(isolated_database, now + timedelta(days=1)).delivered == 0


def test_reconciliation_recovers_post_watermark_jobs_without_duplicate_events(
    isolated_database,
):
    client = account()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    role_slug = "backend-phase23-recovery"
    create_saved_search(
        client,
        isolated_database,
        name="Recover safely",
        role_slug=role_slug,
        watermark=now - timedelta(hours=1),
    )
    job_id, *_ = seed_job(
        isolated_database,
        title="Recovered Internship",
        external_id="recover",
        first_seen_at=now,
        role_slug=role_slug,
    )
    recovered = reconcile(isolated_database, now + timedelta(minutes=1))
    assert recovered.scanned == 1
    assert recovered.created == 1
    assert alert_rows(isolated_database)[0].delivery_state == JobAlertDeliveryState.PENDING
    assert deliver(isolated_database, now + timedelta(minutes=1)).delivered == 1
    assert reconcile(isolated_database, now + timedelta(minutes=2)).created == 0
    assert [row.canonical_job_id for row in alert_rows(isolated_database)] == [job_id]


def test_alert_inbox_is_private_csrf_protected_and_read_state_is_monotonic(
    isolated_database,
):
    owner, other = account(), account()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    role_slug = "backend-phase23-inbox"
    saved = create_saved_search(
        owner,
        isolated_database,
        name="Private inbox",
        role_slug=role_slug,
        watermark=now - timedelta(hours=1),
    )
    job_id, *_ = seed_job(
        isolated_database,
        title="Private inbox internship",
        external_id="private-inbox",
        first_seen_at=now,
        role_slug=role_slug,
    )
    assert evaluate(isolated_database, job_id, now).created == 1
    listed = owner.get(ALERTS_URL)
    assert listed.status_code == 200
    assert listed.headers["cache-control"] == "no-store"
    assert listed.json()["unread_count"] == 1
    assert listed.json()["items"][0]["locations"] == ["Toronto, Ontario, CA"]
    alert_id = listed.json()["items"][0]["id"]
    assert other.get(ALERTS_URL).json() == {"items": [], "unread_count": 0}
    assert other.patch(ALERTS_URL + "/" + alert_id, json={"read": True}, headers=csrf(other)).status_code == 404
    assert owner.patch(ALERTS_URL + "/" + alert_id, json={"read": True}).status_code == 403
    assert owner.patch(
        ALERTS_URL + "/" + alert_id,
        json={"read": True, "user_id": str(user_id(other))},
        headers=csrf(owner),
    ).status_code == 422
    marked = owner.patch(
        ALERTS_URL + "/" + alert_id,
        json={"read": True},
        headers=csrf(owner),
    )
    assert marked.status_code == 200
    assert marked.headers["cache-control"] == "no-store"
    assert marked.json()["read_at"] is not None
    assert owner.get(ALERTS_URL).json()["unread_count"] == 0
    assert owner.patch(
        ALERTS_URL + "/" + alert_id,
        json={"read": False},
        headers=csrf(owner),
    ).status_code == 422
    assert owner.delete(
        SAVED_SEARCHES_URL + "/" + saved["id"],
        headers=csrf(owner),
    ).status_code == 204
    assert not alert_rows(isolated_database)


def test_new_canonical_ingestion_creates_one_fast_alert_but_source_repeats_do_not(
    isolated_database,
):
    client = account()
    role_slug = "software-engineer-phase23-ingestion"
    company_id, role_id = uuid4(), uuid4()
    isolated_database.execute(
        Company.__table__.insert(),
        {"id": company_id, "name": "Ingestion Alert", "is_verified": True},
    )
    isolated_database.execute(
        Role.__table__.insert(),
        {
            "id": role_id,
            "name": "Software Engineer",
            "slug": role_slug,
            "is_active": True,
        },
    )
    create_saved_search(
        client,
        isolated_database,
        name="Ingestion fast path",
        role_slug=role_slug,
        watermark=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    record = ExternalJobDTO(
        adapter_key="fixture.phase23",
        external_id="ingestion-fast-alert",
        source_url="https://jobs.example/ingestion-fast-alert",
        application_url="https://apply.example/ingestion-fast-alert",
        company="Ingestion Alert",
        title="Software Engineer Internship",
        role="Software Engineer",
        employment_type="INTERNSHIP",
        career_level="STUDENT",
        work_mode="HYBRID",
        description="A canonical job used to verify fast alerts.",
        locations=("Toronto, Canada",),
    )
    with UnitOfWork() as uow:
        first_id = JobIngestionService.ingest(
            record, ingestion_registry(record.adapter_key), uow
        ).id
    with UnitOfWork() as uow:
        second_id = JobIngestionService.ingest(
            record, ingestion_registry(record.adapter_key), uow
        ).id
    duplicate_source = record.model_copy(
        update={
            "adapter_key": "fixture.phase23.secondary",
            "external_id": "ingestion-fast-alert-secondary",
            "source_url": "https://jobs.example/ingestion-fast-alert-secondary",
        }
    )
    with UnitOfWork() as uow:
        third_id = JobIngestionService.ingest(
            duplicate_source,
            ingestion_registry(duplicate_source.adapter_key),
            uow,
        ).id

    assert first_id == second_id
    assert third_id == first_id
    rows = alert_rows(isolated_database)
    assert len(rows) == 1
    assert rows[0].canonical_job_id == first_id
    assert rows[0].delivery_state == JobAlertDeliveryState.DELIVERED


def test_database_uniqueness_prevents_concurrent_alert_event_duplicates(database_engine):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    owner_id, search_id, job_id = uuid4(), uuid4(), uuid4()
    company_id, role_id, source_id = uuid4(), uuid4(), uuid4()
    barrier = Barrier(2)
    try:
        with database_engine.begin() as connection:
            connection.execute(
                User.__table__.insert(),
                {
                    "id": owner_id,
                    "email": f"phase23-concurrent-{owner_id.hex}@example.com",
                    "password_hash": "test",
                    "is_active": True,
                },
            )
            connection.execute(
                SavedJobSearch.__table__.insert(),
                {
                    "id": search_id,
                    "user_id": owner_id,
                    "name": "Concurrent safety",
                    "criteria": {},
                    "alert_mode": SavedSearchAlertMode.INSTANT,
                    "alert_enabled_at": now - timedelta(hours=1),
                    "alert_watermark_at": now - timedelta(hours=1),
                    "alert_evaluated_at": now - timedelta(hours=1),
                },
            )
            connection.execute(
                Company.__table__.insert(),
                {"id": company_id, "name": "Concurrent Company", "is_verified": True},
            )
            connection.execute(
                Role.__table__.insert(),
                {
                    "id": role_id,
                    "name": "Concurrent Role",
                    "slug": "concurrent-phase23",
                    "is_active": True,
                },
            )
            connection.execute(
                JobSourceRecord.__table__.insert(),
                {
                    "id": source_id,
                    "source_adapter": "greenhouse",
                    "external_id": "concurrent-phase23",
                    "source_url": "https://source.example/concurrent-phase23",
                },
            )
            connection.execute(
                NormalizedJob.__table__.insert(),
                {
                    "id": job_id,
                    "job_source_record_id": source_id,
                    "company_id": company_id,
                    "role_id": role_id,
                    "title": "Concurrent Internship",
                    "description": "Concurrent alert insert test",
                    "employment_type": "INTERNSHIP",
                    "career_level": "STUDENT",
                    "work_mode": "HYBRID",
                    "application_url": "https://apply.example/concurrent-phase23",
                    "is_active": True,
                    "lifecycle": JobLifecycle.ACTIVE,
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "last_verified_at": now,
                    "canonical_updated_at": now,
                    "discovered_at": now,
                },
            )

        def attempt() -> bool:
            with Session(database_engine) as session:
                barrier.wait()
                created = JobAlertRepository(session).add_alert_if_absent(
                    user_id=owner_id,
                    saved_search_id=search_id,
                    canonical_job_id=job_id,
                    delivery_mode=SavedSearchAlertMode.INSTANT,
                    scheduled_for=now,
                    created_at=now,
                )
                session.commit()
                return created

        with ThreadPoolExecutor(max_workers=2) as executor:
            created = list(executor.map(lambda _: attempt(), range(2)))
        assert created.count(True) == 1
        with Session(database_engine) as session:
            assert session.scalar(
                select(JobAlert.id).where(
                    JobAlert.user_id == owner_id,
                    JobAlert.saved_search_id == search_id,
                    JobAlert.canonical_job_id == job_id,
                )
            )
    finally:
        with database_engine.begin() as connection:
            connection.execute(delete(User).where(User.id == owner_id))
            connection.execute(delete(NormalizedJob).where(NormalizedJob.id == job_id))
            connection.execute(delete(JobSourceRecord).where(JobSourceRecord.id == source_id))
            connection.execute(delete(Role).where(Role.id == role_id))
            connection.execute(delete(Company).where(Company.id == company_id))
