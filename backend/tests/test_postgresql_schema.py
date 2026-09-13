"""High-value PostgreSQL invariants exercised through SQL, not ORM defaults."""

from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import DateTime, inspect, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import IntegrityError


def insert(connection, table, **values):
    columns = ", ".join(values)
    params = ", ".join(":" + key for key in values)
    return (
        connection.execute(
            text(f"INSERT INTO {table} ({columns}) VALUES ({params}) RETURNING *"), values
        )
        .mappings()
        .one()
    )


@pytest.fixture
def graph(isolated_database):
    c = isolated_database
    user = insert(c, "users", email="person@example.edu", password_hash="test-only")["id"]
    resume = insert(c, "resumes", user_id=user, title="Resume")["id"]
    version = insert(
        c,
        "resume_versions",
        resume_id=resume,
        storage_key="version.pdf",
        file_format="PDF",
        file_size_bytes=10,
        file_hash_sha256="a" * 64,
    )["id"]
    role = insert(c, "roles", name="Engineer", slug="engineer")["id"]
    company = insert(c, "companies", name="Example")["id"]
    skill = insert(c, "skills", name="Python", slug="python", category="LANGUAGE")["id"]
    source = insert(
        c,
        "job_source_records",
        source_adapter="MANUAL_ENTRY",
        external_id="job-1",
        source_url="https://example.org/job",
    )["id"]
    job = insert(
        c,
        "normalized_jobs",
        job_source_record_id=source,
        company_id=company,
        role_id=role,
        title="Engineer",
        employment_type="INTERNSHIP",
        application_url="https://example.org/apply",
    )["id"]
    return dict(
        user=user,
        resume=resume,
        version=version,
        role=role,
        company=company,
        skill=skill,
        source=source,
        job=job,
    )


def reject(connection, sqlstate, callback):
    with pytest.raises(IntegrityError) as error, connection.begin_nested():
        callback()
    assert error.value.orig.pgcode == sqlstate


def education(user, month=6, year=2027):
    return dict(
        user_id=user,
        institution_name="University",
        degree_level="BS",
        major="CS",
        study_year="YEAR_3",
        start_date=f"{min(2024, year):04d}-01-01",
        expected_grad_month=month,
        expected_grad_year=year,
    )


@pytest.mark.parametrize("month,year", [(0, 2027), (13, 2027), (6, 1999), (6, 2101)])
def test_graduation_bounds_rejected(isolated_database, graph, month, year):
    reject(
        isolated_database,
        "23514",
        lambda: insert(
            isolated_database, "education_records", **education(graph["user"], month, year)
        ),
    )


@pytest.mark.parametrize("month,year", [(1, 2000), (12, 2100)])
def test_graduation_boundaries_accepted(isolated_database, graph, month, year):
    insert(isolated_database, "education_records", **education(graph["user"], month, year))


def test_email_case_uniqueness(isolated_database, graph):
    reject(
        isolated_database,
        "23505",
        lambda: insert(isolated_database, "users", email="PERSON@example.edu", password_hash="x"),
    )


def test_employment_documented_invariant(isolated_database, graph):
    values = dict(
        user_id=graph["user"], employer_name="Example", job_title="Intern", start_date="2025-01-01"
    )
    reject(
        isolated_database,
        "23514",
        lambda: insert(isolated_database, "employment_records", **values),
    )
    insert(isolated_database, "employment_records", **values, currently_employed=True)
    insert(isolated_database, "employment_records", **values, end_date="2025-08-01")
    # The approved OR rule does not forbid an end date when currently_employed=True.
    insert(
        isolated_database,
        "employment_records",
        **values,
        currently_employed=True,
        end_date="2025-08-01",
    )


def test_source_snapshot_and_authorization_uniqueness(isolated_database, graph):
    c = isolated_database
    reject(
        c,
        "23505",
        lambda: insert(
            c,
            "job_source_records",
            source_adapter="MANUAL_ENTRY",
            external_id="job-1",
            source_url="https://example.org/another",
        ),
    )
    insert(
        c,
        "job_source_records",
        source_adapter="SEED_FIXTURE",
        external_id="job-1",
        source_url="https://example.org/job",
    )
    snapshot = dict(
        job_source_record_id=graph["source"],
        payload_hash_sha256="b" * 64,
        raw_payload='{"title": "Engineer"}',
    )
    insert(c, "raw_job_snapshots", **snapshot)
    reject(c, "23505", lambda: insert(c, "raw_job_snapshots", **snapshot))
    auth = dict(user_id=graph["user"], country_code="US", authorization_status="CITIZEN")
    insert(c, "work_authorizations", **auth)
    reject(c, "23505", lambda: insert(c, "work_authorizations", **auth))
    insert(c, "work_authorizations", **{**auth, "country_code": "CA"})


def test_resume_primary_version_and_evidence_uniqueness(isolated_database, graph):
    c = isolated_database
    values = dict(
        resume_id=graph["resume"],
        storage_key="next.pdf",
        file_format="PDF",
        file_size_bytes=10,
        file_hash_sha256="c" * 64,
    )
    reject(c, "23505", lambda: insert(c, "resume_versions", **values))
    c.execute(
        text("UPDATE resume_versions SET is_primary_active = true WHERE id = :id"),
        {"id": graph["version"]},
    )
    reject(
        c,
        "23505",
        lambda: insert(c, "resume_versions", **values, version_number=2, is_primary_active=True),
    )
    insert(c, "resume_versions", **values, version_number=2, is_primary_active=False)
    other = insert(c, "resumes", user_id=graph["user"], title="Other")["id"]
    insert(c, "resume_versions", **{**values, "resume_id": other}, is_primary_active=True)
    item = insert(
        c,
        "resume_evidence_items",
        resume_version_id=graph["version"],
        category="PROJECTS",
        bullet_text="Built Python project",
        ordinal=0,
    )["id"]
    evidence = dict(evidence_item_id=item, skill_id=graph["skill"])
    insert(c, "resume_evidence_skills", **evidence)
    reject(c, "23505", lambda: insert(c, "resume_evidence_skills", **evidence))


@pytest.mark.parametrize(
    "changes",
    [
        {"version_number": 0},
        {"file_size_bytes": 0},
        {"file_size_bytes": 5 * 1024 * 1024 + 1},
        {"file_format": "TXT"},
        {"parse_status": "UNKNOWN"},
        {"file_hash_sha256": "A" * 64},
    ],
)
def test_resume_version_upload_invariants_are_durable(isolated_database, graph, changes):
    values = dict(
        resume_id=graph["resume"],
        version_number=2,
        storage_key="managed-version.pdf",
        file_format="PDF",
        file_size_bytes=10,
        file_hash_sha256="b" * 64,
        parse_status="PENDING",
    )
    reject(
        isolated_database,
        "23514",
        lambda: insert(isolated_database, "resume_versions", **{**values, **changes}),
    )


@pytest.mark.parametrize("score", [-1, 101])
def test_evaluation_score_rejected(isolated_database, graph, score):
    reject(
        isolated_database,
        "23514",
        lambda: insert(
            isolated_database,
            "resume_evaluations",
            resume_version_id=graph["version"],
            evaluation_type="GENERAL_QUALITY",
            rubric_version="1",
            overall_score=score,
            category_scores="{}",
            itemized_reasons=[],
            suggested_improvements=[],
        ),
    )


@pytest.mark.parametrize("score", [0, 100])
def test_evaluation_score_boundaries(isolated_database, graph, score):
    insert(
        isolated_database,
        "resume_evaluations",
        resume_version_id=graph["version"],
        evaluation_type="GENERAL_QUALITY",
        rubric_version="1",
        overall_score=score,
        category_scores="{}",
        itemized_reasons=[],
        suggested_improvements=[],
    )


@pytest.mark.parametrize("version", [0, -1])
def test_application_version_rejected(isolated_database, graph, version):
    reject(
        isolated_database,
        "23514",
        lambda: insert(
            isolated_database,
            "applications",
            user_id=graph["user"],
            job_id=graph["job"],
            current_status="APPLIED",
            version=version,
        ),
    )


def test_application_uniqueness_defaults_and_immutable_resume_association(isolated_database, graph):
    c = isolated_database
    values = dict(user_id=graph["user"], job_id=graph["job"], current_status="APPLIED")
    app = insert(
        c,
        "applications",
        **values,
        resume_version_id=graph["version"],
        resume_title_snapshot="Historic resume",
        resume_hash_snapshot="a" * 64,
    )
    assert app["version"] == 1
    reject(c, "23505", lambda: insert(c, "applications", **values))
    reject(
        c,
        "23503",
        lambda: c.execute(text("DELETE FROM resume_versions WHERE id = :id"), {"id": graph["version"]}),
    )
    result = (
        c.execute(text("SELECT * FROM applications WHERE id = :id"), {"id": app["id"]})
        .mappings()
        .one()
    )
    assert result["resume_version_id"] == graph["version"]
    assert result["resume_title_snapshot"] == "Historic resume"
    assert result["resume_hash_snapshot"] == "a" * 64


def test_delete_restrict_cascade_and_set_null(isolated_database, graph):
    c = isolated_database
    reject(
        c,
        "23503",
        lambda: c.execute(text("DELETE FROM companies WHERE id = :id"), {"id": graph["company"]}),
    )
    reject(
        c,
        "23503",
        lambda: c.execute(text("DELETE FROM roles WHERE id = :id"), {"id": graph["role"]}),
    )
    location = insert(c, "locations", country_code="US", city="Denver")["id"]
    job_location = insert(
        c, "job_locations", job_id=graph["job"], location_id=location, location_raw="Denver"
    )["id"]
    c.execute(text("DELETE FROM locations WHERE id = :id"), {"id": location})
    assert (
        c.execute(
            text("SELECT location_id FROM job_locations WHERE id = :id"), {"id": job_location}
        ).scalar_one()
        is None
    )
    app = insert(
        c, "applications", user_id=graph["user"], job_id=graph["job"], current_status="APPLIED"
    )["id"]
    insert(c, "application_status_histories", application_id=app, new_status="APPLIED")
    c.execute(text("DELETE FROM users WHERE id = :id"), {"id": graph["user"]})
    for table in ["resumes", "resume_versions", "applications", "application_status_histories"]:
        assert c.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0


def test_native_types_indexes_and_fk_metadata(isolated_database):
    inspector = inspect(isolated_database)
    for table in inspector.get_table_names():
        if table == "alembic_version":
            continue
        for column in inspector.get_columns(table):
            if (
                column["name"] == "id"
                or column["name"].endswith("_id")
                and column["name"] != "external_id"
            ):
                assert isinstance(column["type"], PG_UUID), (table, column["name"])
            if isinstance(column["type"], DateTime):
                assert column["type"].timezone, (table, column["name"])
    for table, names in [
        ("raw_job_snapshots", ["raw_payload"]),
        ("resume_evaluations", ["category_scores", "bullet_analysis_detail"]),
    ]:
        cols = {col["name"]: col for col in inspector.get_columns(table)}
        assert all(isinstance(cols[name]["type"], JSONB) for name in names)
    for table, names in [
        ("career_preferences", ["work_modes", "employment_types"]),
        ("resume_evaluations", ["itemized_reasons", "suggested_improvements"]),
    ]:
        cols = {col["name"]: col for col in inspector.get_columns(table)}
        assert all(isinstance(cols[name]["type"], ARRAY) for name in names)
    primary = next(
        i
        for i in inspector.get_indexes("resume_versions")
        if i["name"] == "idx_user_primary_resume_version"
    )
    assert primary["unique"] and primary["column_names"] == ["resume_id"]
    assert "is_primary_active" in primary["dialect_options"]["postgresql_where"]
    for table, column, action in [
        ("applications", "resume_version_id", "RESTRICT"),
        ("normalized_jobs", "company_id", "RESTRICT"),
        ("resumes", "user_id", "CASCADE"),
    ]:
        fk = next(
            f for f in inspector.get_foreign_keys(table) if f["constrained_columns"] == [column]
        )
        assert fk["options"]["ondelete"] == action


def test_server_defaults_and_aware_round_trip(isolated_database, graph):
    c = isolated_database
    user = (
        c.execute(text("SELECT * FROM users WHERE id = :id"), {"id": graph["user"]})
        .mappings()
        .one()
    )
    assert isinstance(user["id"], UUID)
    assert user["is_active"] is True
    assert user["created_at"].utcoffset() is not None
    instant = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
    c.execute(
        text("UPDATE users SET created_at = :instant WHERE id = :id"),
        {"instant": instant, "id": graph["user"]},
    )
    c.exec_driver_sql("SET LOCAL TIME ZONE 'America/Denver'")
    actual = c.execute(
        text("SELECT created_at FROM users WHERE id = :id"), {"id": graph["user"]}
    ).scalar_one()
    assert actual == instant
    job = (
        c.execute(text("SELECT * FROM normalized_jobs WHERE id = :id"), {"id": graph["job"]})
        .mappings()
        .one()
    )
    assert job["work_mode"] == job["career_level"] == "UNSPECIFIED"


def test_session_token_index_and_uniqueness(isolated_database, graph):
    inspector = inspect(isolated_database)
    indexes = inspector.get_indexes("user_sessions")
    token_indexes = [index for index in indexes if index["column_names"] == ["session_token_hash"]]
    assert len(token_indexes) == 1
    assert token_indexes[0]["unique"]
    assert not {"idx_user_sessions_lookup", "ix_user_sessions_expires_at"} & {
        i["name"] for i in indexes
    }
    assert any(i["column_names"] == ["user_id"] for i in indexes)
    values = dict(
        user_id=graph["user"],
        session_token_hash="1" * 64,
        csrf_token_hash="2" * 64,
        expires_at=datetime.now(timezone.utc),
    )
    insert(isolated_database, "user_sessions", **values)
    reject(isolated_database, "23505", lambda: insert(isolated_database, "user_sessions", **values))
