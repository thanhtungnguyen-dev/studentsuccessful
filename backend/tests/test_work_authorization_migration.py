"""Constraints preserve valid legal facts and block unsupported legacy rows."""
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

HEAD = "e94a6db32571"
PREVIOUS = "d83f5ca21460"
CHECKS = {"ck_work_authorization_country_code", "ck_work_authorization_status"}


@pytest.fixture
def previous_schema(database_engine):
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with database_engine.connect() as connection:
        transaction = connection.begin()
        schema = "work_authorization_migration_" + uuid4().hex
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
    fields = dict(user_id=owner, country_code="CA", authorization_status="OTHER")
    fields.update(changes)
    return connection.execute(text(f"INSERT INTO work_authorizations ({', '.join(fields)}) VALUES ({', '.join(':'+key for key in fields)}) RETURNING *"), fields).mappings().one()


def test_upgrade_downgrade_preserves_rows_and_unique(previous_schema):
    c, cfg, schema, owner = previous_schema
    for country, status in [("CA", "CITIZEN"), ("US", "STUDENT_VISA_CPT_OPT"), ("GB", "WORK_VISA"), ("FR", "PERMANENT_RESIDENT"), ("DE", "OTHER")]:
        insert(c, owner, country_code=country, authorization_status=status)
    before = [dict(row) for row in c.execute(text("SELECT * FROM work_authorizations ORDER BY id")).mappings()]
    command.upgrade(cfg, HEAD)
    assert {x["name"] for x in inspect(c).get_check_constraints("work_authorizations", schema=schema)} == CHECKS
    assert any(x["name"] == "uq_work_auth_user_country" for x in inspect(c).get_unique_constraints("work_authorizations", schema=schema))
    assert [dict(row) for row in c.execute(text("SELECT * FROM work_authorizations ORDER BY id")).mappings()] == before
    for country, status in [("AU", "STUDENT_WORK_AUTHORIZATION"), ("NZ", "TEMPORARY_WORK_AUTHORIZATION")]:
        insert(c, owner, country_code=country, authorization_status=status)
    all_rows = [dict(row) for row in c.execute(text("SELECT * FROM work_authorizations ORDER BY id")).mappings()]
    command.downgrade(cfg, PREVIOUS)
    assert inspect(c).get_check_constraints("work_authorizations", schema=schema) == []
    assert [dict(row) for row in c.execute(text("SELECT * FROM work_authorizations ORDER BY id")).mappings()] == all_rows
    command.upgrade(cfg, HEAD)
    with pytest.raises(IntegrityError) as error, c.begin_nested():
        insert(c, owner)
    assert error.value.orig.pgcode == "23505"
    other = uuid4()
    c.execute(text("INSERT INTO users (id,email,password_hash) VALUES (:id,'other@example.com','test')"), {"id": other})
    insert(c, other)


@pytest.mark.parametrize("changes", [{"country_code": "ca"}, {"country_code": "C"}, {"country_code": "1A"}, {"country_code": "éA"}, {"authorization_status": "UNSUPPORTED"}])
def test_direct_sql_rejected(previous_schema, changes):
    c, cfg, _, owner = previous_schema
    command.upgrade(cfg, HEAD)
    with pytest.raises(IntegrityError) as error, c.begin_nested():
        insert(c, owner, **changes)
    assert error.value.orig.pgcode == "23514"


@pytest.mark.parametrize("changes", [{"country_code": "ca"}, {"authorization_status": "UNSUPPORTED"}])
def test_legacy_invalid_blocks_transaction_without_repair(previous_schema, changes):
    c, cfg, schema, owner = previous_schema
    original = dict(insert(c, owner, **changes))
    with pytest.raises(IntegrityError), c.begin_nested():
        command.upgrade(cfg, HEAD)
    assert dict(c.execute(text("SELECT * FROM work_authorizations")).mappings().one()) == original
    assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == PREVIOUS
    assert inspect(c).get_check_constraints("work_authorizations", schema=schema) == []
