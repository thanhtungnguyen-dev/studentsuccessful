"""Employment date-order migration preserves facts and the accepted OR rule."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

HEAD = "d83f5ca21460"
PREVIOUS = "c72e4b9d103f"


@pytest.fixture
def previous_schema(database_engine):
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with database_engine.connect() as connection:
        transaction = connection.begin()
        schema = "employment_migration_" + uuid4().hex
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        cfg.attributes["connection"] = connection
        try:
            command.upgrade(cfg, PREVIOUS)
            owner = uuid4()
            connection.execute(text("INSERT INTO users (id,email,password_hash) VALUES (:id,'migration@example.com','test')"), {"id": owner})
            yield connection, cfg, schema, owner
        finally:
            transaction.rollback()


def insert(connection, owner, **changes):
    fields = dict(user_id=owner, employer_name="Employer", job_title="Developer", start_date="2026-01-01", currently_employed=True)
    fields.update(changes)
    return connection.execute(text(f"INSERT INTO employment_records ({', '.join(fields)}) VALUES ({', '.join(':'+key for key in fields)}) RETURNING *"), fields).mappings().one()


def test_upgrade_downgrade_preserve_rows_and_old_constraint(previous_schema):
    connection, cfg, schema, owner = previous_schema
    insert(connection, owner)
    insert(connection, owner, end_date="2027-05-01")
    insert(connection, owner, currently_employed=False, end_date="2026-08-31")
    before = [dict(row) for row in connection.execute(text("SELECT * FROM employment_records ORDER BY id")).mappings()]
    old_checks = {item["name"]: item["sqltext"] for item in inspect(connection).get_check_constraints("employment_records", schema=schema)}
    command.upgrade(cfg, HEAD)
    checks = {item["name"]: item["sqltext"] for item in inspect(connection).get_check_constraints("employment_records", schema=schema)}
    assert checks.keys() == old_checks.keys() | {"ck_employment_date_order"}
    assert checks["ck_employment_end_date"] == old_checks["ck_employment_end_date"]
    assert [dict(row) for row in connection.execute(text("SELECT * FROM employment_records ORDER BY id")).mappings()] == before
    assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == HEAD
    command.downgrade(cfg, PREVIOUS)
    assert {item["name"]: item["sqltext"] for item in inspect(connection).get_check_constraints("employment_records", schema=schema)} == old_checks
    assert [dict(row) for row in connection.execute(text("SELECT * FROM employment_records ORDER BY id")).mappings()] == before
    command.upgrade(cfg, HEAD)


@pytest.mark.parametrize("values", [{"currently_employed": False}, {"end_date": "2025-12-31"}, {"currently_employed": False, "end_date": "2025-12-31"}])
def test_database_rejects_invalid_states(previous_schema, values):
    connection, cfg, _, owner = previous_schema
    command.upgrade(cfg, HEAD)
    with pytest.raises(IntegrityError), connection.begin_nested():
        insert(connection, owner, **values)


def test_reversed_legacy_dates_block_upgrade_without_repair(previous_schema):
    connection, cfg, schema, owner = previous_schema
    original = dict(insert(connection, owner, end_date="2025-12-31"))
    with pytest.raises(IntegrityError), connection.begin_nested():
        command.upgrade(cfg, HEAD)
    assert dict(connection.execute(text("SELECT * FROM employment_records")).mappings().one()) == original
    assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == PREVIOUS
    assert "ck_employment_date_order" not in {item["name"] for item in inspect(connection).get_check_constraints("employment_records", schema=schema)}
