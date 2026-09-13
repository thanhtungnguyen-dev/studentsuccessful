"""Focused Phase 24 official Apply and private manual application tracking."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.main import app
from backend.app.models.application import Application, ApplicationStatusHistory
from backend.app.models.job import (
    JobAlert,
    JobAlertDeliveryState,
    JobLifecycle,
    JobSourceRecord,
    NormalizedJob,
    SavedJobSearch,
)
from backend.app.models.resume import Resume, ResumeVersion
from backend.app.models.taxonomy import Company, Role
from backend.app.models.user import User
from backend.app.schemas.application import ApplicationUpdate
from backend.app.services.application import ApplicationService

APPLICATIONS_URL = "/api/v1/applications"
JOBS_URL = "/api/v1/jobs"


def account() -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"phase24-{uuid4().hex}@example.com", "password": "Phase24-password-123!"},
    )
    assert response.status_code == 201, response.text
    return client


def csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["ss_csrf"]}


def owner_id(client: TestClient) -> UUID:
    return UUID(client.get("/api/v1/auth/me").json()["id"])


def seed_job(connection, *, title: str = "Platform Engineering Intern", url: str | None = None):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    company_id, role_id, source_id, job_id = (uuid4() for _ in range(4))
    external_id = uuid4().hex
    connection.execute(
        Company.__table__.insert(),
        {"id": company_id, "name": title + " Company", "is_verified": True},
    )
    connection.execute(
        Role.__table__.insert(),
        {"id": role_id, "name": "Platform", "slug": "platform-" + external_id, "is_active": True},
    )
    connection.execute(
        JobSourceRecord.__table__.insert(),
        {
            "id": source_id,
            "source_adapter": "greenhouse",
            "external_id": external_id,
            "source_url": "https://source.example/" + external_id,
        },
    )
    connection.execute(
        NormalizedJob.__table__.insert(),
        {
            "id": job_id,
            "job_source_record_id": source_id,
            "company_id": company_id,
            "title": title,
            "description": "Official canonical opening",
            "role_id": role_id,
            "employment_type": "INTERNSHIP",
            "career_level": "STUDENT",
            "work_mode": "HYBRID",
            "application_url": url or "https://apply.example/" + external_id,
            "is_active": True,
            "lifecycle": JobLifecycle.ACTIVE,
            "first_seen_at": now,
            "last_seen_at": now,
            "last_verified_at": now,
            "canonical_updated_at": now,
            "discovered_at": now,
        },
    )
    return job_id, company_id, source_id


def seed_alert(connection, *, user_id: UUID, job_id: UUID):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    search_id, alert_id = uuid4(), uuid4()
    connection.execute(
        SavedJobSearch.__table__.insert(),
        {
            "id": search_id,
            "user_id": user_id,
            "name": "Phase 24 alerts",
            "criteria": {},
            "alert_mode": "OFF",
        },
    )
    connection.execute(
        JobAlert.__table__.insert(),
        {
            "id": alert_id,
            "user_id": user_id,
            "saved_search_id": search_id,
            "canonical_job_id": job_id,
            "delivery_mode": "INSTANT",
            "delivery_state": JobAlertDeliveryState.DELIVERED,
            "scheduled_for": now,
            "delivered_at": now,
        },
    )


def seed_resume_version(connection, *, user_id: UUID, title: str = "Phase 24 Resume"):
    resume_id, version_id = uuid4(), uuid4()
    connection.execute(Resume.__table__.insert(), {"id": resume_id, "user_id": user_id, "title": title})
    connection.execute(
        ResumeVersion.__table__.insert(),
        {
            "id": version_id,
            "resume_id": resume_id,
            "version_number": 1,
            "storage_key": "private/" + uuid4().hex + ".pdf",
            "file_format": "PDF",
            "file_size_bytes": 512,
            "file_hash_sha256": "a" * 64,
            "is_primary_active": True,
            "parse_status": "PENDING",
        },
    )
    return resume_id, version_id


def mark_applied(client: TestClient, job_id: UUID, **extra):
    response = client.post(
        APPLICATIONS_URL,
        json={"canonical_job_id": str(job_id), **extra},
        headers=csrf(client),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_feed_detail_and_alert_share_canonical_apply_without_creating_application(isolated_database):
    client = account()
    job_id, _, _ = seed_job(isolated_database)
    seed_alert(isolated_database, user_id=owner_id(client), job_id=job_id)

    feed = client.get(JOBS_URL)
    detail = client.get(JOBS_URL + "/" + str(job_id))
    alerts = client.get("/api/v1/alerts")

    assert feed.status_code == detail.status_code == alerts.status_code == 200
    destination = feed.json()["items"][0]["application_url"]
    assert detail.json()["application_url"] == destination
    assert alerts.json()["items"][0]["application_url"] == destination
    assert feed.headers["cache-control"] == "no-store"
    assert isolated_database.scalar(select(func.count()).select_from(Application)) == 0


def test_explicit_mark_applied_creates_initial_history_and_respects_applied_date(isolated_database):
    client = account()
    job_id, _, _ = seed_job(isolated_database)
    recorded_at = "2026-09-11T12:30:00Z"

    application = mark_applied(
        client,
        job_id,
        applied_at=recorded_at,
        notes="Recruiter screen requested",
    )

    assert application["current_status"] == "APPLIED"
    assert application["applied_at"] == recorded_at
    assert application["notes"] == "Recruiter screen requested"
    assert [(event["previous_status"], event["new_status"]) for event in application["history"]] == [
        (None, "APPLIED")
    ]
    assert application["job_title"] == "Platform Engineering Intern"
    assert application["company_name"] == "Platform Engineering Intern Company"


def test_duplicate_tracking_is_prevented_but_other_users_can_track_same_job(isolated_database):
    client, other = account(), account()
    job_id, _, _ = seed_job(isolated_database)
    first = mark_applied(client, job_id)

    duplicate = client.post(
        APPLICATIONS_URL,
        json={"canonical_job_id": str(job_id)},
        headers=csrf(client),
    )
    second = mark_applied(other, job_id)

    assert duplicate.status_code == 409
    assert second["id"] != first["id"]
    assert isolated_database.scalar(select(func.count()).select_from(Application)) == 2


def test_resume_version_is_optional_owned_and_historically_snapshotted(isolated_database):
    client, other = account(), account()
    own_resume_id, own_version_id = seed_resume_version(
        isolated_database, user_id=owner_id(client), title="Backend Resume"
    )
    _, other_version_id = seed_resume_version(isolated_database, user_id=owner_id(other))
    first_job, _, _ = seed_job(isolated_database, title="Resume-linked opening")
    second_job, _, _ = seed_job(isolated_database, title="No-resume opening")
    third_job, _, _ = seed_job(isolated_database, title="Foreign-resume opening")

    linked = mark_applied(client, first_job, resume_version_id=str(own_version_id))
    optional = mark_applied(client, second_job)
    rejected = client.post(
        APPLICATIONS_URL,
        json={"canonical_job_id": str(third_job), "resume_version_id": str(other_version_id)},
        headers=csrf(client),
    )
    isolated_database.execute(
        update(Resume).where(Resume.id == own_resume_id).values(title="Renamed after applying")
    )

    reread = client.get(APPLICATIONS_URL + "/" + linked["id"])
    delete_linked_version = client.delete(
        "/api/v1/resume-versions/" + str(own_version_id),
        headers=csrf(client),
    )
    assert linked["resume_version_id"] == str(own_version_id)
    assert optional["resume_version_id"] is None
    assert rejected.status_code == 404
    assert delete_linked_version.status_code == 409
    assert reread.json()["resume_title"] == "Backend Resume"


def test_permissive_manual_statuses_append_immutable_history(isolated_database):
    client = account()
    jobs = [seed_job(isolated_database, title="Status " + status)[0] for status in ("Offer", "Rejected", "Withdrawn")]
    offer, rejected, withdrawn = (mark_applied(client, job) for job in jobs)

    interview = client.patch(
        APPLICATIONS_URL + "/" + offer["id"],
        json={"expected_version": offer["version"], "status": "INTERVIEW", "status_note": "Screen booked"},
        headers=csrf(client),
    )
    offered = client.patch(
        APPLICATIONS_URL + "/" + offer["id"],
        json={"expected_version": interview.json()["version"], "status": "OFFER"},
        headers=csrf(client),
    )
    direct_rejection = client.patch(
        APPLICATIONS_URL + "/" + rejected["id"],
        json={"expected_version": rejected["version"], "status": "REJECTED"},
        headers=csrf(client),
    )
    withdrawal = client.patch(
        APPLICATIONS_URL + "/" + withdrawn["id"],
        json={"expected_version": withdrawn["version"], "status": "WITHDRAWN"},
        headers=csrf(client),
    )

    assert [response.status_code for response in (interview, offered, direct_rejection, withdrawal)] == [200, 200, 200, 200]
    assert offered.json()["current_status"] == "OFFER"
    assert [(event["previous_status"], event["new_status"]) for event in offered.json()["history"]] == [
        (None, "APPLIED"),
        ("APPLIED", "INTERVIEW"),
        ("INTERVIEW", "OFFER"),
    ]
    assert interview.json()["history"][1]["notes"] == "Screen booked"
    assert direct_rejection.json()["current_status"] == "REJECTED"
    assert withdrawal.json()["current_status"] == "WITHDRAWN"


def test_stale_and_retried_status_updates_do_not_overwrite_or_duplicate_history(isolated_database):
    client = account()
    application = mark_applied(client, seed_job(isolated_database)[0])

    current = client.patch(
        APPLICATIONS_URL + "/" + application["id"],
        json={"expected_version": application["version"], "status": "INTERVIEW"},
        headers=csrf(client),
    )
    stale = client.patch(
        APPLICATIONS_URL + "/" + application["id"],
        json={"expected_version": application["version"], "status": "REJECTED"},
        headers=csrf(client),
    )
    retry = client.patch(
        APPLICATIONS_URL + "/" + application["id"],
        json={"expected_version": current.json()["version"], "status": "INTERVIEW"},
        headers=csrf(client),
    )

    assert current.status_code == retry.status_code == 200
    assert stale.status_code == 409
    assert retry.json()["current_status"] == "INTERVIEW"
    assert retry.json()["version"] == current.json()["version"]
    assert len(retry.json()["history"]) == 2


def test_simultaneous_transitions_use_revision_conflict_instead_of_lost_update(database_engine):
    """Two sessions starting from one revision may commit only one transition."""
    user_id, application_id = uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    with database_engine.begin() as connection:
        connection.execute(
            User.__table__.insert(),
            {"id": user_id, "email": "concurrent-" + uuid4().hex + "@example.com", "password_hash": "test"},
        )
        job_id, company_id, source_id = seed_job(connection, title="Concurrent application")
        role_id = connection.scalar(
            select(NormalizedJob.role_id).where(NormalizedJob.id == job_id)
        )
        connection.execute(
            Application.__table__.insert(),
            {
                "id": application_id,
                "user_id": user_id,
                "job_id": job_id,
                "job_title_snapshot": "Concurrent application",
                "company_name_snapshot": "Concurrent application Company",
                "current_status": "APPLIED",
                "version": 1,
                "applied_at": now,
            },
        )
        connection.execute(
            ApplicationStatusHistory.__table__.insert(),
            {
                "id": uuid4(),
                "application_id": application_id,
                "previous_status": None,
                "new_status": "APPLIED",
                "transitioned_at": now,
            },
        )
    factory = sessionmaker(bind=database_engine)
    barrier = Barrier(2)

    def transition(status: str):
        barrier.wait()
        with UnitOfWork(session_factory=factory) as uow:
            try:
                return ApplicationService.update(
                    user_id,
                    application_id,
                    ApplicationUpdate(expected_version=1, status=status),
                    uow,
                )
            except StudentSuccessfulException as exc:
                return exc

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(transition, ("INTERVIEW", "REJECTED")))
        successes = [result for result in results if not isinstance(result, StudentSuccessfulException)]
        conflicts = [result for result in results if isinstance(result, StudentSuccessfulException)]
        with database_engine.connect() as connection:
            current = connection.execute(
                select(Application.current_status, Application.version).where(Application.id == application_id)
            ).one()
            history_count = connection.scalar(
                select(func.count()).select_from(ApplicationStatusHistory).where(
                    ApplicationStatusHistory.application_id == application_id
                )
            )
        assert len(successes) == 1
        assert len(conflicts) == 1
        assert conflicts[0].status_code == 409
        assert current.version == 2
        assert current.current_status in {"INTERVIEW", "REJECTED"}
        assert history_count == 2
    finally:
        with database_engine.begin() as connection:
            connection.execute(delete(User).where(User.id == user_id))
            connection.execute(delete(JobSourceRecord).where(JobSourceRecord.id == source_id))
            connection.execute(delete(Company).where(Company.id == company_id))
            connection.execute(delete(Role).where(Role.id == role_id))


def test_closed_hidden_and_saved_jobs_do_not_change_or_remove_application(isolated_database):
    client = account()
    job_id, _, source_id = seed_job(isolated_database)
    application = mark_applied(client, job_id)

    for payload in ({"saved": True}, {"hidden": True}):
        response = client.patch(JOBS_URL + "/" + str(job_id) + "/state", json=payload, headers=csrf(client))
        assert response.status_code == 200, response.text
    isolated_database.execute(
        update(NormalizedJob)
        .where(NormalizedJob.id == job_id)
        .values(is_active=False, lifecycle=JobLifecycle.CLOSED)
    )
    isolated_database.execute(
        update(JobSourceRecord).where(JobSourceRecord.id == source_id).values(source_url="https://source.example/unavailable")
    )

    read = client.get(APPLICATIONS_URL + "/" + application["id"])
    listed = client.get(APPLICATIONS_URL)
    assert read.status_code == listed.status_code == 200
    assert read.json()["current_status"] == "APPLIED"
    assert read.json()["job_lifecycle"] == "CLOSED"
    assert [item["id"] for item in listed.json()["items"]] == [application["id"]]


def test_applications_are_private_and_csrf_protected(isolated_database):
    client, other = account(), account()
    job_id, _, _ = seed_job(isolated_database)
    application = mark_applied(client, job_id)

    own_without_csrf = client.post(APPLICATIONS_URL, json={"canonical_job_id": str(uuid4())})
    foreign_get = other.get(APPLICATIONS_URL + "/" + application["id"])
    foreign_patch = other.patch(
        APPLICATIONS_URL + "/" + application["id"],
        json={"expected_version": application["version"], "status": "REJECTED"},
        headers=csrf(other),
    )
    forged_owner = client.post(
        APPLICATIONS_URL,
        json={"canonical_job_id": str(job_id), "user_id": str(owner_id(other))},
        headers=csrf(client),
    )

    assert own_without_csrf.status_code == 403
    assert foreign_get.status_code == foreign_patch.status_code == 404
    assert forged_owner.status_code == 422


def test_database_rejects_unsafe_apply_destination_and_unknown_application_status(isolated_database):
    with pytest.raises(IntegrityError):
        with isolated_database.begin_nested():
            seed_job(isolated_database, url="javascript:alert(1)")
    job_id, _, _ = seed_job(isolated_database)
    application = mark_applied(account(), job_id)
    with pytest.raises(IntegrityError):
        with isolated_database.begin_nested():
            isolated_database.execute(
                update(Application)
                .where(Application.id == UUID(application["id"]))
                .values(current_status="SAVED")
            )


def test_history_rows_are_never_rewritten_by_status_changes(isolated_database):
    client = account()
    application = mark_applied(client, seed_job(isolated_database)[0])
    first_history = client.get(APPLICATIONS_URL + "/" + application["id"]).json()["history"][0]
    updated = client.patch(
        APPLICATIONS_URL + "/" + application["id"],
        json={"expected_version": application["version"], "status": "INTERVIEW"},
        headers=csrf(client),
    ).json()

    persisted = isolated_database.execute(
        select(ApplicationStatusHistory.previous_status, ApplicationStatusHistory.new_status)
        .where(ApplicationStatusHistory.id == UUID(first_history["id"]))
    ).one()
    assert persisted == (None, "APPLIED")
    assert len(updated["history"]) == 2
