"""PostgreSQL-only upgrade/downgrade safety and durable Education constraints."""

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

HEAD = "c72e4b9d103f"
PREVIOUS = "b61f0a2c9d34"


@pytest.fixture
def previous_schema(database_engine):
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with database_engine.connect() as connection:
        transaction = connection.begin()
        schema = "education_migration_" + uuid4().hex
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        cfg.attributes["connection"] = connection
        try:
            command.upgrade(cfg, PREVIOUS)
            owner = uuid4()
            connection.execute(text("INSERT INTO users (id, email, password_hash) VALUES (:id, 'edu-migration@example.com', 'test')"), {"id": owner})
            yield connection, cfg, schema, owner
        finally:
            transaction.rollback()


def insert_education(connection, owner, **changes):
    fields = dict(user_id=owner, institution_name="University", degree_level="BS", major="CS", study_year="YEAR_3", start_date="2024-09-01", expected_grad_month=6, expected_grad_year=2028)
    fields.update(changes)
    return connection.execute(text(f"INSERT INTO education_records ({', '.join(fields)}) VALUES ({', '.join(':' + key for key in fields)}) RETURNING *"), fields).mappings().one()


def test_precision_preservation_and_both_downgrade_paths(previous_schema):
    connection, cfg, schema, owner = previous_schema
    before = dict(insert_education(connection, owner, gpa_value=Decimal("3.54"), gpa_scale=Decimal("4.00"), gpa_include_on_apps=True))
    command.upgrade(cfg, HEAD)
    assert dict(connection.execute(text("SELECT * FROM education_records")).mappings().one()) == before
    columns = {item["name"]: item for item in inspect(connection).get_columns("education_records", schema=schema)}
    for name in ("gpa_value", "gpa_scale"):
        assert (columns[name]["type"].precision, columns[name]["type"].scale) == (5, 2)
    assert columns["is_primary"]["default"] == "false"
    assert "uq_education_primary_user" in {item["name"] for item in inspect(connection).get_indexes("education_records", schema=schema)}
    assert {"ck_education_gpa_pair", "ck_education_gpa_nonnegative", "ck_education_gpa_scale_positive", "ck_education_gpa_within_scale", "ck_education_gpa_disclosure", "ck_education_date_order"} <= {item["name"] for item in inspect(connection).get_check_constraints("education_records", schema=schema)}
    connection.execute(text("UPDATE education_records SET gpa_value=100.00, gpa_scale=100.00"))
    with pytest.raises(DBAPIError, match="downgrade blocked"), connection.begin_nested():
        command.downgrade(cfg, PREVIOUS)
    assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == HEAD
    row = connection.execute(text("SELECT gpa_value, gpa_scale FROM education_records")).one()
    assert tuple(row) == (Decimal("100.00"), Decimal("100.00"))
    assert any(item["name"] == "uq_education_primary_user" for item in inspect(connection).get_indexes("education_records", schema=schema))
    connection.execute(text("UPDATE education_records SET gpa_value=99.99"))
    command.downgrade(cfg, PREVIOUS)
    assert connection.execute(text("SELECT gpa_value FROM education_records")).scalar_one() == Decimal("99.99")
    columns = {item["name"]: item for item in inspect(connection).get_columns("education_records", schema=schema)}
    assert (columns["gpa_value"]["type"].precision, columns["gpa_value"]["type"].scale) == (4, 2)
    command.upgrade(cfg, HEAD)


@pytest.mark.parametrize("changes", [
    {"gpa_value": Decimal("3.54")}, {"gpa_scale": Decimal("4.00")},
    {"gpa_value": Decimal("-1.00"), "gpa_scale": Decimal("4.00")},
    {"gpa_value": Decimal("0.00"), "gpa_scale": Decimal("0.00")},
    {"gpa_value": Decimal("5.00"), "gpa_scale": Decimal("4.00")},
    {"gpa_include_on_apps": True}, {"start_date": "2029-01-01"},
    {"gpa_value": Decimal("NaN"), "gpa_scale": Decimal("NaN")},
])
def test_new_checks_reject_direct_sql(previous_schema, changes):
    connection, cfg, _, owner = previous_schema
    command.upgrade(cfg, HEAD)
    with pytest.raises(IntegrityError), connection.begin_nested():
        insert_education(connection, owner, **changes)
    assert connection.execute(text("SELECT count(*) FROM education_records")).scalar_one() == 0


def test_partial_unique_index_and_false_server_default(previous_schema):
    connection, cfg, _, owner = previous_schema
    command.upgrade(cfg, HEAD)
    assert insert_education(connection, owner)["is_primary"] is False
    assert insert_education(connection, owner)["is_primary"] is False
    insert_education(connection, owner, is_primary=True)
    with pytest.raises(IntegrityError), connection.begin_nested():
        insert_education(connection, owner, is_primary=True)


@pytest.mark.parametrize("problem", ["duplicate_primary", "half_pair", "disclosure", "date_order"])
def test_upgrade_refuses_conflicting_legacy_data_without_repair(previous_schema, problem):
    connection, cfg, schema, owner = previous_schema
    changes = {"half_pair": {"gpa_value": Decimal("3.54")}, "disclosure": {"gpa_include_on_apps": True}, "date_order": {"start_date": "2030-01-01"}}.get(problem, {})
    insert_education(connection, owner, **changes)
    if problem == "duplicate_primary":
        insert_education(connection, owner)  # The old default TRUE allowed this conflict.
    before = [dict(row) for row in connection.execute(text("SELECT * FROM education_records ORDER BY id")).mappings()]
    with pytest.raises(IntegrityError), connection.begin_nested():
        command.upgrade(cfg, HEAD)
    assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == PREVIOUS
    assert [dict(row) for row in connection.execute(text("SELECT * FROM education_records ORDER BY id")).mappings()] == before
    columns = {item["name"]: item for item in inspect(connection).get_columns("education_records", schema=schema)}
    assert columns["gpa_value"]["type"].precision == 4
