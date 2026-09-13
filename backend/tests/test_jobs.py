"""Public shared job browsing stays independent of candidates and applications."""

from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event, text

from backend.app.main import app
from backend.app.models.job import (
    JobEducationRequirement,
    JobEligibilityRequirement,
    JobLocation,
    JobSkillRequirement,
    JobSourceRecord,
    NormalizedJob,
)
from backend.app.models.taxonomy import Company, Role, Skill
from backend.app.repositories.job import JobRepository
from backend.app.services.job import JobSearch

URL = "/api/v1/jobs"


def account():
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"jobs-{uuid4().hex}@example.com", "password": "Jobs-password-123!"},
    )
    assert response.status_code == 201
    return client


def seed_job(
    connection,
    *,
    title: str,
    external_id: str,
    posted_at: datetime | None,
    description: str | None = None,
    active: bool = True,
    locations: list[str] | None = None,
    company_name: str | None = None,
    role_name: str | None = None,
    employment_type: str = "INTERNSHIP",
    work_mode: str = "REMOTE",
):
    company_id, role_id, source_id, job_id = uuid4(), uuid4(), uuid4(), uuid4()
    connection.execute(
        Company.__table__.insert(),
        {"id": company_id, "name": company_name or f"{title} Company", "is_verified": True},
    )
    connection.execute(
        Role.__table__.insert(),
        {
            "id": role_id,
            "name": role_name or f"{title} Role",
            "slug": f"role-{external_id}",
            "is_active": True,
        },
    )
    connection.execute(
        JobSourceRecord.__table__.insert(),
        {
            "id": source_id,
            "source_adapter": "TEST",
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
            "description": description,
            "role_id": role_id,
            "employment_type": employment_type,
            "career_level": "STUDENT",
            "work_mode": work_mode,
            "application_url": f"https://apply.example/{external_id}",
            "is_active": active,
            "posted_at": posted_at,
        },
    )
    location_rows = [
        {"id": uuid4(), "job_id": job_id, "location_raw": location}
        for location in locations or []
    ]
    if location_rows:
        connection.execute(JobLocation.__table__.insert(), location_rows)
    return job_id


def test_public_active_jobs_list_and_detail_in_deterministic_order(isolated_database):
    client = account()
    old = seed_job(
        isolated_database,
        title="Older job",
        external_id="old",
        posted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    newest = seed_job(
        isolated_database,
        title="Newest job",
        external_id="new",
        posted_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        description="A normalized plain-text summary.",
        locations=["Toronto, ON", "Remote"],
    )
    seed_job(
        isolated_database,
        title="Unpublished job",
        external_id="inactive",
        posted_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        active=False,
    )

    response = client.get(URL)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    listing = response.json()
    assert {key: listing[key] for key in ("page", "page_size", "total", "total_pages")} == {
        "page": 1,
        "page_size": 10,
        "total": 2,
        "total_pages": 1,
    }
    assert [row["id"] for row in listing["items"]] == [str(newest), str(old)]
    assert listing["items"][0] == {
        "id": str(newest),
        "title": "Newest job",
        "description": "A normalized plain-text summary.",
        "company_id": listing["items"][0]["company_id"],
        "company_name": "Newest job Company",
        "role_id": listing["items"][0]["role_id"],
        "role_name": "Newest job Role",
        "employment_type": "INTERNSHIP",
        "career_level": "STUDENT",
        "work_mode": "REMOTE",
        "source_name": "Official careers site",
        "application_url": "https://apply.example/new",
        "posted_at": "2026-02-01T00:00:00Z",
        "discovered_at": listing["items"][0]["discovered_at"],
        "first_seen_at": listing["items"][0]["first_seen_at"],
        "last_seen_at": listing["items"][0]["last_seen_at"],
        "last_verified_at": listing["items"][0]["last_verified_at"],
        "canonical_updated_at": listing["items"][0]["canonical_updated_at"],
        "lifecycle": "NEW",
        "saved": False,
        "hidden": False,
        "viewed_at": None,
        "unseen": True,
        "matched_filters": [],
    }
    detail = client.get(f"{URL}/{newest}")
    assert detail.status_code == 200
    assert detail.headers["cache-control"] == "no-store"
    assert detail.json()["locations"] == ["Remote", "Toronto, ON"]
    assert detail.json()["id"] == str(newest)
    assert detail.json()["skill_requirements"] == []
    assert detail.json()["education_requirements"] == []
    assert detail.json()["eligibility_requirements"] == []


def test_inactive_and_unknown_jobs_share_safe_not_found_response(isolated_database):
    client = account()
    inactive = seed_job(
        isolated_database,
        title="Inactive job",
        external_id="inactive",
        posted_at=None,
        active=False,
    )
    hidden = client.get(f"{URL}/{inactive}")
    missing = client.get(f"{URL}/{uuid4()}")
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json()["code"] == missing.json()["code"] == "JOB_NOT_FOUND"
    assert hidden.json()["detail"] == missing.json()["detail"] == "Job not found"


def test_public_job_payload_never_contains_candidate_or_application_data(isolated_database):
    client = account()
    job_id = seed_job(
        isolated_database,
        title="Independent job",
        external_id="independent",
        posted_at=None,
        locations=["Anywhere"],
    )
    payload = client.get(f"{URL}/{job_id}").json()
    assert payload["locations"] == ["Anywhere"]
    assert not (
        {
            "user_id",
            "application_id",
            "resume_version_id",
            "score",
            "fit",
            "job_source_record_id",
            "source_adapter",
            "source_url",
            "raw_payload",
            "payload_hash_sha256",
        }
        & payload.keys()
    )


def test_job_detail_returns_ordered_safe_normalized_requirements(isolated_database):
    client = account()
    job_id = seed_job(
        isolated_database,
        title="Requirements job",
        external_id="requirements",
        posted_at=None,
    )
    docker_id, python_id = uuid4(), uuid4()
    isolated_database.execute(
        Skill.__table__.insert(),
        [
            {"id": python_id, "name": "Python", "slug": "python-job", "category": "TECHNOLOGY"},
            {"id": docker_id, "name": "Docker", "slug": "docker-job", "category": "TECHNOLOGY"},
        ],
    )
    isolated_database.execute(
        JobSkillRequirement.__table__.insert(),
        [
            {"id": uuid4(), "job_id": job_id, "skill_id": python_id, "importance": "PREFERRED", "description": "Python experience"},
            {"id": uuid4(), "job_id": job_id, "skill_id": docker_id, "importance": "REQUIRED", "description": None},
        ],
    )
    isolated_database.execute(
        JobEducationRequirement.__table__.insert(),
        {
            "id": uuid4(),
            "job_id": job_id,
            "degree_level": "BS",
            "target_grad_start": date(2026, 5, 1),
            "target_grad_end": date(2027, 5, 1),
        },
    )
    eligibility_id = uuid4()
    isolated_database.execute(
        JobEligibilityRequirement.__table__.insert(),
        {
            "id": eligibility_id,
            "job_id": job_id,
            "requirement_type": "WORK_AUTHORIZATION",
            "value": "CA",
            "description": "Eligible to work in Canada",
            "source_evidence": "private ingestion provenance",
        },
    )

    detail = client.get(f"{URL}/{job_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert [item["skill_name"] for item in payload["skill_requirements"]] == ["Docker", "Python"]
    assert payload["skill_requirements"][0]["importance"] == "REQUIRED"
    assert payload["education_requirements"] == [{
        "id": payload["education_requirements"][0]["id"],
        "degree_level": "BS",
        "target_grad_start": "2026-05-01",
        "target_grad_end": "2027-05-01",
    }]
    assert payload["eligibility_requirements"] == [{
        "id": str(eligibility_id),
        "requirement_type": "WORK_AUTHORIZATION",
        "value": "CA",
        "description": "Eligible to work in Canada",
    }]
    assert "source_evidence" not in str(payload)


def test_jobs_require_authentication_and_reject_client_owner_query(isolated_database):
    client = account()
    job_id = seed_job(
        isolated_database,
        title="Authenticated job",
        external_id="auth",
        posted_at=None,
    )
    unauthenticated_list = TestClient(app).get(URL)
    unauthenticated_detail = TestClient(app).get(f"{URL}/{job_id}")
    assert unauthenticated_list.status_code == unauthenticated_detail.status_code == 401
    assert unauthenticated_list.headers["cache-control"] == "no-store"
    assert unauthenticated_detail.headers["cache-control"] == "no-store"
    assert client.get(f"{URL}?user_id={uuid4()}").status_code == 422


def test_job_discovery_searches_public_catalog_fields_and_filters(isolated_database):
    client = account()
    platform = seed_job(
        isolated_database,
        title="Platform Python Intern",
        external_id="platform-python",
        posted_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        description="Build reliable distributed services.",
        company_name="Acme Labs",
        employment_type="INTERNSHIP",
        work_mode="REMOTE",
        locations=["Toronto, Canada", "Remote"],
    )
    analyst = seed_job(
        isolated_database,
        title="Reporting Analyst",
        external_id="reporting-analyst",
        posted_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        description="Use Python for business reporting.",
        company_name="Northwind",
        employment_type="FULL_TIME",
        work_mode="HYBRID",
        locations=["Calgary, Canada"],
    )
    designer = seed_job(
        isolated_database,
        title="On-site Designer",
        external_id="designer",
        posted_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        description="Design clear product experiences.",
        company_name="Acme Labs",
        employment_type="PART_TIME",
        work_mode="ON_SITE",
        locations=["Vancouver, Canada"],
    )
    skill_id = uuid4()
    isolated_database.execute(
        Skill.__table__.insert(),
        {"id": skill_id, "name": "PostgreSQL", "slug": "postgresql-search", "category": "DATABASE"},
    )
    isolated_database.execute(
        JobSkillRequirement.__table__.insert(),
        {
            "id": uuid4(),
            "job_id": platform,
            "skill_id": skill_id,
            "importance": "REQUIRED",
            "description": "Database query experience",
        },
    )

    def found(**params):
        response = client.get(URL, params=params)
        assert response.status_code == 200, response.text
        return [row["id"] for row in response.json()["items"]]

    acme = [str(designer), str(platform)]
    assert found(keyword="platform") == [str(platform)]
    assert found(query="distributed") == [str(platform)]
    assert found(keyword="python") == [str(analyst), str(platform)]
    assert found(company="ACME") == acme
    assert found(location="calgary") == [str(analyst)]
    assert found(requirement="postgres") == [str(platform)]
    assert found(requirement="database query") == [str(platform)]
    assert found(type="internship") == [str(platform)]
    assert found(employment_type="full-time") == [str(analyst)]
    assert found(work_mode="on-site") == [str(designer)]
    assert found(keyword="python", location="toronto", company="acme", requirement="postgres") == [
        str(platform)
    ]


def test_job_discovery_paginates_sorts_and_returns_an_explicit_empty_page(isolated_database):
    client = account()
    alpha = seed_job(
        isolated_database,
        title="Alpha role",
        external_id="alpha",
        posted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    bravo = seed_job(
        isolated_database,
        title="Bravo role",
        external_id="bravo",
        posted_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    charlie = seed_job(
        isolated_database,
        title="Charlie role",
        external_id="charlie",
        posted_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )

    first = client.get(URL, params={"sort": "title_asc", "page": 1, "page_size": 2})
    assert first.status_code == 200
    assert first.json() == {
        "items": [
            {**first.json()["items"][0], "id": str(alpha), "title": "Alpha role"},
            {**first.json()["items"][1], "id": str(bravo), "title": "Bravo role"},
        ],
        "page": 1,
        "page_size": 2,
        "total": 3,
        "total_pages": 2,
    }
    second = client.get(URL, params={"sort": "title_asc", "page": 2, "page_size": 2})
    assert second.status_code == 200
    assert [row["id"] for row in second.json()["items"]] == [str(charlie)]
    assert second.json()["total"] == 3
    assert [
        row["id"] for row in client.get(URL, params={"sort": "oldest"}).json()["items"]
    ] == [str(alpha), str(bravo), str(charlie)]
    empty = client.get(URL, params={"keyword": "not-present"})
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "page": 1, "page_size": 10, "total": 0, "total_pages": 0}


def test_job_discovery_rejects_invalid_or_ambiguous_parameters(isolated_database):
    client = account()
    job_id = seed_job(
        isolated_database,
        title="Validation job",
        external_id="validation",
        posted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    invalid = (
        {"page": 0},
        {"page_size": 51},
        {"sort": "score"},
        {"type": "recommended"},
        {"work_mode": "global"},
        {"keyword": "x" * 101},
        {"source_url": "private"},
        {"user_id": str(uuid4())},
        {"keyword": "python", "query": "python"},
        {"employment_type": "INTERNSHIP", "type": "INTERNSHIP"},
    )
    for params in invalid:
        response = client.get(URL, params=params)
        assert response.status_code == 422, response.text
        assert response.headers["cache-control"] == "no-store"
    repeated = client.get(f"{URL}?keyword=one&keyword=two")
    assert repeated.status_code == 422
    detail_query = client.get(f"{URL}/{job_id}", params={"keyword": "one"})
    assert detail_query.status_code == 422


def test_job_discovery_treats_search_text_as_literal_bound_data(isolated_database):
    client = account()
    percent = seed_job(
        isolated_database,
        title="100% Platform Engineer",
        external_id="percent",
        posted_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    underscore = seed_job(
        isolated_database,
        title="Under_score Engineer",
        external_id="underscore",
        posted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert [row["id"] for row in client.get(URL, params={"keyword": "%"}).json()["items"]] == [
        str(percent)
    ]
    assert [row["id"] for row in client.get(URL, params={"keyword": "_"}).json()["items"]] == [
        str(underscore)
    ]
    injection = client.get(URL, params={"keyword": "%' OR TRUE --"})
    assert injection.status_code == 200
    assert injection.json()["items"] == []


def test_job_discovery_uses_two_catalog_queries_and_has_its_listing_index(isolated_database):
    for number in range(12):
        seed_job(
            isolated_database,
            title=f"Query count job {number}",
            external_id=f"query-count-{number}",
            posted_at=datetime(2026, 1, number + 1, tzinfo=timezone.utc),
        )

    statements: list[str] = []

    def capture(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(isolated_database, "before_cursor_execute", capture)
    try:
        total, rows = JobRepository(isolated_database).search_active(JobSearch(page=2, page_size=5))
    finally:
        event.remove(isolated_database, "before_cursor_execute", capture)

    assert total == 12
    assert len(rows) == 5
    assert len([statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]) == 2
    indexes = set(
        isolated_database.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = current_schema() AND tablename = 'normalized_jobs'"
            )
        ).scalars()
    )
    assert "idx_normalized_jobs_active_listing" in indexes
