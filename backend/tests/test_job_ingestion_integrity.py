"""PostgreSQL checks added by the job-ingestion integrity migration."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from backend.app.models import Base

INTEGRITY_HEAD = "e7d1b9f4a2c3"
CURRENT_HEAD = "d27e8f0a213b"
PREVIOUS = "f3d9a7b1c5e2"
CHECKS = {
    "job_source_records": {
        "ck_job_source_adapter_safe",
        "ck_job_source_external_id_safe",
        "ck_job_source_url_http",
    },
    "raw_job_snapshots": {"ck_job_snapshot_hash_sha256"},
    "normalized_jobs": {
        "ck_normalized_job_application_url_http",
        "ck_normalized_job_current_hash_sha256",
    },
}


def insert(connection, table, **values):
    columns = ", ".join(values)
    params = ", ".join(":" + key for key in values)
    return connection.execute(
        text(f"INSERT INTO {table} ({columns}) VALUES ({params}) RETURNING *"), values
    ).mappings().one()


@pytest.fixture
def previous_schema(database_engine):
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with database_engine.connect() as connection:
        transaction = connection.begin()
        schema = "job_ingestion_integrity_" + uuid4().hex
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        cfg.attributes["connection"] = connection
        try:
            command.upgrade(cfg, PREVIOUS)
            yield connection, cfg, schema
        finally:
            transaction.rollback()


def job_graph(connection, *, source_adapter="fixture.ats", external_id="opening-123"):
    source = insert(
        connection,
        "job_source_records",
        source_adapter=source_adapter,
        external_id=external_id,
        source_url="https://jobs.example.test/opening-123",
    )["id"]
    company = insert(connection, "companies", name="Example Corp")["id"]
    role = insert(connection, "roles", name="Engineer", slug="engineer")["id"]
    job = insert(
        connection,
        "normalized_jobs",
        job_source_record_id=source,
        company_id=company,
        role_id=role,
        title="Engineer",
        employment_type="INTERNSHIP",
        application_url="https://apply.example.test/opening-123",
    )["id"]
    return source, job


def reject_check(connection, callback):
    with pytest.raises(IntegrityError) as error, connection.begin_nested():
        callback()
    assert error.value.orig.pgcode == "23514"


def test_upgrade_downgrade_preserves_valid_existing_style_job_rows(previous_schema):
    connection, cfg, schema = previous_schema
    source, job = job_graph(connection)
    snapshot = insert(
        connection,
        "raw_job_snapshots",
        job_source_record_id=source,
        raw_payload='{"title": "Engineer"}',
        payload_hash_sha256="a" * 64,
    )["id"]
    before = {
        table: [dict(row) for row in connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).mappings()]
        for table in ("job_source_records", "raw_job_snapshots", "normalized_jobs")
    }

    command.upgrade(cfg, INTEGRITY_HEAD)
    assert {
        table: {item["name"] for item in inspect(connection).get_check_constraints(table, schema=schema)}
        for table in CHECKS
    } == CHECKS
    upgraded = {
        table: [dict(row) for row in connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).mappings()]
        for table in before
    }
    for row in upgraded["normalized_jobs"]:
        assert row.pop("current_payload_hash_sha256") is None
    assert upgraded == before

    command.downgrade(cfg, PREVIOUS)
    assert all(
        inspect(connection).get_check_constraints(table, schema=schema) == [] for table in CHECKS
    )
    assert connection.execute(text("SELECT id FROM normalized_jobs WHERE id = :id"), {"id": job}).scalar_one() == job
    assert connection.execute(text("SELECT id FROM raw_job_snapshots WHERE id = :id"), {"id": snapshot}).scalar_one() == snapshot


@pytest.mark.parametrize(
    "table,values",
    [
        ("job_source_records", {"source_adapter": "   ", "external_id": "ok", "source_url": "https://example.test/job"}),
        ("job_source_records", {"source_adapter": "fixture\nats", "external_id": "ok", "source_url": "https://example.test/job"}),
        ("job_source_records", {"source_adapter": "fixture.ats", "external_id": "\t", "source_url": "https://example.test/job"}),
        ("job_source_records", {"source_adapter": "fixture.ats", "external_id": "ok", "source_url": "http://example.test/a b"}),
        ("job_source_records", {"source_adapter": "fixture.ats", "external_id": "ok", "source_url": "ftp://example.test/job"}),
        ("raw_job_snapshots", {"job_source_record_id": "source", "raw_payload": "{}", "payload_hash_sha256": "A" * 64}),
        ("raw_job_snapshots", {"job_source_record_id": "source", "raw_payload": "{}", "payload_hash_sha256": "a" * 63}),
        ("normalized_jobs", {"job_source_record_id": "source", "company_id": "company", "role_id": "role", "title": "Engineer", "employment_type": "INTERNSHIP", "application_url": "https://apply.example.test/a b"}),
        ("normalized_jobs", {"job_source_record_id": "source", "company_id": "company", "role_id": "role", "title": "Engineer", "employment_type": "INTERNSHIP", "application_url": "mailto:recruiter@example.test"}),
        ("normalized_jobs", {"job_source_record_id": "source", "company_id": "company", "role_id": "role", "title": "Engineer", "employment_type": "INTERNSHIP", "application_url": "https://apply.example.test/opening-123", "current_payload_hash_sha256": "A" * 64}),
        ("normalized_jobs", {"job_source_record_id": "source", "company_id": "company", "role_id": "role", "title": "Engineer", "employment_type": "INTERNSHIP", "application_url": "https://apply.example.test/opening-123", "current_payload_hash_sha256": "a" * 63}),
    ],
)
def test_direct_database_writes_reject_malformed_ingestion_facts(previous_schema, table, values):
    connection, cfg, _ = previous_schema
    command.upgrade(cfg, INTEGRITY_HEAD)
    source, _ = job_graph(connection, external_id="valid-source")
    company = connection.execute(text("SELECT id FROM companies")).scalar_one()
    role = connection.execute(text("SELECT id FROM roles")).scalar_one()
    values = {key: {"source": source, "company": company, "role": role}.get(value, value) for key, value in values.items()}
    reject_check(connection, lambda: insert(connection, table, **values))


def test_current_head_matches_models(database_engine):
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    assert ScriptDirectory.from_config(cfg).get_heads() == [CURRENT_HEAD]
    with database_engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "compare_server_default": True}
        )
        assert context.get_current_heads() == (CURRENT_HEAD,)
        assert compare_metadata(context, Base.metadata) == []
