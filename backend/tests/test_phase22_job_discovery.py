"""Phase 22 filter-first canonical feed, private state, and saved-search tests."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event, select

from backend.app.main import app
from backend.app.models.job import (
    JobLifecycle,
    JobLocation,
    JobSourceObservation,
    JobSourceRecord,
    NormalizedJob,
    UserJobState,
)
from backend.app.models.taxonomy import Company, Location, Role
from backend.app.repositories.job import JobRepository
from backend.app.services.job import JobSearch

JOBS_URL = "/api/v1/jobs"
SAVED_SEARCHES_URL = "/api/v1/saved-searches"


def account() -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"phase22-{uuid4().hex}@example.com", "password": "Phase22-password-123!"},
    )
    assert response.status_code == 201
    return client


def csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["ss_csrf"]}


def seed_job(
    connection,
    *,
    title: str,
    slug: str,
    external_id: str,
    first_seen_at: datetime,
    country: str | None = None,
    region: str | None = None,
    city: str | None = None,
    employment_type: str = "INTERNSHIP",
    work_mode: str = "REMOTE",
    lifecycle: str = JobLifecycle.ACTIVE,
    is_active: bool = True,
):
    company_id, role_id, source_id, job_id = uuid4(), uuid4(), uuid4(), uuid4()
    connection.execute(
        Company.__table__.insert(),
        {"id": company_id, "name": f"{title} Company", "is_verified": True},
    )
    connection.execute(
        Role.__table__.insert(),
        {"id": role_id, "name": slug.replace("-", " ").title(), "slug": f"{slug}-{external_id}", "is_active": True},
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
            "description": f"{title} description",
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
                "location_raw": ", ".join(part for part in (city, region, country) if part),
            },
        )
    return job_id, company_id, role_id, source_id


def test_structured_filters_use_or_within_fields_and_and_across_fields(isolated_database):
    client = account()
    now = datetime.now(timezone.utc)
    backend, *_ = seed_job(
        isolated_database,
        title="Backend Intern",
        slug="backend",
        external_id="backend",
        first_seen_at=now - timedelta(minutes=20),
        country="CA",
        region="Ontario",
        city="Toronto",
        work_mode="HYBRID",
    )
    platform, *_ = seed_job(
        isolated_database,
        title="Platform Intern",
        slug="platform",
        external_id="platform",
        first_seen_at=now - timedelta(minutes=10),
        country="US",
        region="Washington",
        city="Seattle",
    )
    seed_job(
        isolated_database,
        title="Frontend Intern",
        slug="frontend",
        external_id="frontend",
        first_seen_at=now - timedelta(days=4),
        country="CA",
        region="Ontario",
        city="Toronto",
    )
    seed_job(
        isolated_database,
        title="Closed Backend Intern",
        slug="backend",
        external_id="closed",
        first_seen_at=now - timedelta(minutes=5),
        country="CA",
        region="Ontario",
        city="Toronto",
        lifecycle=JobLifecycle.CLOSED,
        is_active=False,
    )
    unknown_location, *_ = seed_job(
        isolated_database,
        title="Unstructured Canada Intern",
        slug="backend",
        external_id="unstructured",
        first_seen_at=now - timedelta(minutes=15),
    )
    isolated_database.execute(
        JobLocation.__table__.insert(),
        {
            "id": uuid4(),
            "job_id": unknown_location,
            "location_id": None,
            "location_raw": "Toronto, Canada",
        },
    )

    response = client.get(
        JOBS_URL,
        params=[
            ("role", "backend-backend"),
            ("role", "platform-platform"),
            ("country", "CA"),
            ("job_type", "internship"),
            ("work_mode", "REMOTE"),
            ("work_mode", "HYBRID"),
            ("recency", "24h"),
        ],
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [row["id"] for row in payload["items"]] == [str(backend)]
    assert payload["items"][0]["matched_filters"] == [
        "Role: Backend Backend, Platform Platform",
        "Country: CA",
        "Job type: Internship",
        "Work mode: Remote, Hybrid",
        "First seen: Last 24 hours",
    ]

    role_or = client.get(JOBS_URL, params=[("role", "backend-backend"), ("role", "platform-platform")])
    assert [row["id"] for row in role_or.json()["items"]][:2] == [str(platform), str(backend)]
    assert client.get(JOBS_URL, params={"country": "CA"}).json()["total"] == 2
    assert client.get(JOBS_URL, params={"region": "Ontario", "city": "Toronto"}).json()["total"] == 2


def test_feed_is_canonical_newest_first_and_paginates_stably(isolated_database):
    client = account()
    first_seen = datetime.now(timezone.utc) - timedelta(hours=2)
    jobs = [
        seed_job(
            isolated_database,
            title=f"Canonical {number}",
            slug="backend",
            external_id=f"canonical-{number}",
            first_seen_at=first_seen + timedelta(minutes=number),
        )
        for number in range(5)
    ]
    job_id, company_id, role_id, _ = jobs[-1]
    observation_source = uuid4()
    isolated_database.execute(
        JobSourceRecord.__table__.insert(),
        {
            "id": observation_source,
            "source_adapter": "lever",
            "external_id": "duplicate-observation",
            "source_url": "https://source.example/duplicate-observation",
        },
    )
    isolated_database.execute(
        JobSourceObservation.__table__.insert(),
        {
            "id": uuid4(),
            "canonical_job_id": job_id,
            "job_source_record_id": observation_source,
            "source_authority": "OFFICIAL_ATS",
            "source_url": "https://source.example/duplicate-observation",
            "application_url": "https://apply.example/duplicate-observation",
            "source_url_fingerprint": "a" * 64,
            "application_url_fingerprint": "b" * 64,
            "company_id": company_id,
            "role_id": role_id,
            "title": "Canonical 4",
            "description": "An additional source observation",
            "employment_type": "INTERNSHIP",
            "career_level": "STUDENT",
            "work_mode": "REMOTE",
        },
    )

    page_one = client.get(JOBS_URL, params={"page": 1, "page_size": 2})
    page_two = client.get(JOBS_URL, params={"page": 2, "page_size": 2})
    page_three = client.get(JOBS_URL, params={"page": 3, "page_size": 2})
    assert page_one.status_code == page_two.status_code == page_three.status_code == 200
    all_ids = [
        *(row["id"] for row in page_one.json()["items"]),
        *(row["id"] for row in page_two.json()["items"]),
        *(row["id"] for row in page_three.json()["items"]),
    ]
    assert len(all_ids) == len(set(all_ids)) == 5
    assert all_ids == [str(item[0]) for item in reversed(jobs)]
    assert page_one.json()["total"] == 5
    assert page_three.json()["total_pages"] == 3


def test_private_save_hide_and_viewed_state_are_isolated_per_user(isolated_database):
    owner, other = account(), account()
    job_id, *_ = seed_job(
        isolated_database,
        title="Private State Job",
        slug="backend",
        external_id="private-state",
        first_seen_at=datetime.now(timezone.utc),
        country="CA",
    )
    assert owner.patch(
        f"{JOBS_URL}/{job_id}/state",
        json={"saved": True},
        headers=csrf(owner),
    ).json() == {
        "job_id": str(job_id),
        "saved": True,
        "hidden": False,
        "viewed_at": None,
        "unseen": True,
    }
    viewed = owner.patch(
        f"{JOBS_URL}/{job_id}/state",
        json={"viewed": True},
        headers=csrf(owner),
    )
    assert viewed.status_code == 200
    assert viewed.json()["saved"] is True
    assert viewed.json()["unseen"] is False
    assert viewed.json()["viewed_at"] is not None
    hidden = owner.patch(
        f"{JOBS_URL}/{job_id}/state",
        json={"hidden": True},
        headers=csrf(owner),
    )
    assert hidden.status_code == 200
    assert owner.get(JOBS_URL).json()["items"] == []
    assert [row["id"] for row in owner.get(JOBS_URL, params={"view": "saved"}).json()["items"]] == []
    assert [row["id"] for row in owner.get(JOBS_URL, params={"view": "hidden"}).json()["items"]] == [
        str(job_id)
    ]
    assert other.get(JOBS_URL).json()["items"][0]["saved"] is False
    assert other.get(JOBS_URL).json()["items"][0]["hidden"] is False
    assert other.get(JOBS_URL).json()["items"][0]["unseen"] is True

    unhidden = owner.patch(
        f"{JOBS_URL}/{job_id}/state",
        json={"hidden": False},
        headers=csrf(owner),
    )
    assert unhidden.status_code == 200
    assert owner.get(JOBS_URL, params={"view": "saved"}).json()["items"][0]["saved"] is True
    job = isolated_database.execute(
        select(NormalizedJob.is_active, NormalizedJob.lifecycle).where(NormalizedJob.id == job_id)
    ).one()
    assert job.is_active is True
    assert job.lifecycle == JobLifecycle.ACTIVE
    assert isolated_database.execute(
        select(UserJobState).where(UserJobState.canonical_job_id == job_id)
    ).scalars().all()


def test_job_state_requires_csrf_and_never_uses_a_client_owner(isolated_database):
    owner, other = account(), account()
    job_id, *_ = seed_job(
        isolated_database,
        title="CSRF Job",
        slug="backend",
        external_id="csrf",
        first_seen_at=datetime.now(timezone.utc),
    )
    path = f"{JOBS_URL}/{job_id}/state"
    assert owner.patch(path, json={"saved": True}).status_code == 403
    assert owner.patch(
        path,
        json={"saved": True, "user_id": other.get("/api/v1/auth/me").json()["id"]},
        headers=csrf(owner),
    ).status_code == 422
    assert other.patch(path, json={"saved": True}, headers=csrf(other)).status_code == 200
    assert owner.get(JOBS_URL).json()["items"][0]["saved"] is False
    assert other.get(JOBS_URL).json()["items"][0]["saved"] is True


def test_saved_searches_preserve_normalized_criteria_and_enforce_ownership(isolated_database):
    owner, other = account(), account()
    payload = {
        "name": "  Canada backend internships  ",
        "criteria": {
            "roles": ["Backend"],
            "countries": ["ca"],
            "regions": [" Ontario "],
            "cities": ["Toronto"],
            "job_types": ["internship"],
            "work_modes": ["remote", "hybrid"],
            "recency": "24h",
            "keyword": "  API platform ",
            "company": " Example ",
            "requirement": "Python",
        },
    }
    created = owner.post(SAVED_SEARCHES_URL, json=payload, headers=csrf(owner))
    assert created.status_code == 201, created.text
    saved = created.json()
    search_id = saved["id"]
    assert saved["name"] == "Canada backend internships"
    assert saved["criteria"] == {
        "roles": ["backend"],
        "countries": ["CA"],
        "regions": ["Ontario"],
        "cities": ["Toronto"],
        "job_types": ["INTERNSHIP"],
        "work_modes": ["REMOTE", "HYBRID"],
        "recency": "24h",
        "keyword": "API platform",
        "company": "Example",
        "requirement": "Python",
    }
    assert owner.get(SAVED_SEARCHES_URL).json()[0]["id"] == search_id
    assert other.get(SAVED_SEARCHES_URL).json() == []
    assert other.get(f"{SAVED_SEARCHES_URL}/{search_id}").status_code == 404
    assert other.patch(
        f"{SAVED_SEARCHES_URL}/{search_id}",
        json={"name": "Other user"},
        headers=csrf(other),
    ).status_code == 404
    assert other.delete(f"{SAVED_SEARCHES_URL}/{search_id}", headers=csrf(other)).status_code == 404
    invalid = owner.post(
        SAVED_SEARCHES_URL,
        json={"name": "Invalid", "criteria": {"recency": "forever"}},
        headers=csrf(owner),
    )
    assert invalid.status_code == 422
    assert owner.post(
        SAVED_SEARCHES_URL,
        json={"name": "No owner override", "criteria": {}, "user_id": str(uuid4())},
        headers=csrf(owner),
    ).status_code == 422

    updated = owner.patch(
        f"{SAVED_SEARCHES_URL}/{search_id}",
        json={"name": "Canada roles", "criteria": {"roles": ["platform"], "recency": "7d"}},
        headers=csrf(owner),
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Canada roles"
    assert updated.json()["criteria"]["roles"] == ["platform"]
    assert updated.json()["criteria"]["recency"] == "7d"
    assert owner.delete(f"{SAVED_SEARCHES_URL}/{search_id}", headers=csrf(owner)).status_code == 204
    assert owner.get(SAVED_SEARCHES_URL).json() == []


def test_feed_uses_two_queries_when_enriching_current_user_state(isolated_database):
    client = account()
    user_id = client.get("/api/v1/auth/me").json()["id"]
    for number in range(3):
        seed_job(
            isolated_database,
            title=f"Query job {number}",
            slug="backend",
            external_id=f"query-{number}",
            first_seen_at=datetime.now(timezone.utc) - timedelta(minutes=number),
        )
    statements: list[str] = []

    def capture(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(isolated_database, "before_cursor_execute", capture)
    try:
        total, rows = JobRepository(isolated_database).search_active(
            JobSearch(page=1, page_size=2),
            user_id,
        )
    finally:
        event.remove(isolated_database, "before_cursor_execute", capture)
    assert total == 3
    assert len(rows) == 2
    assert len([statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]) == 2
