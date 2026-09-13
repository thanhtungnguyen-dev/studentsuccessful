"""Narrow preference checks preserve valid data and reject incompatible legacy facts."""
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

PREVIOUS = "e94a6db32571"
HEAD = "fa5b7ec43682"


@pytest.fixture
def previous_schema(database_engine):
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with database_engine.connect() as connection:
        transaction = connection.begin()
        schema = "preferences_migration_" + uuid4().hex
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




def insert(c, owner, modes=None, types=None, custom_type="ROLE"):
    id = c.execute(text("INSERT INTO career_preferences(user_id,work_modes,employment_types) VALUES (:owner,:modes,:types) RETURNING id"), {"owner": owner, "modes": modes if modes is not None else ["REMOTE"], "types": types if types is not None else ["INTERNSHIP"]}).scalar_one()
    c.execute(text("INSERT INTO career_preference_custom_values(career_preference_id,preference_type,value,normalized_value) VALUES (:id,:type,' My Role ','my role')"), {"id": id, "type": custom_type})


def rows(c):
    return [list(c.execute(text("SELECT * FROM " + table + " ORDER BY id")).mappings()) for table in ["career_preferences", "career_preference_custom_values"]]


def test_upgrade_downgrade_preserves_facts(previous_schema):
    c, cfg, schema, owner = previous_schema
    insert(c, owner)
    before = rows(c)
    command.upgrade(cfg, HEAD)
    assert {x["name"] for x in inspect(c).get_check_constraints("career_preferences", schema=schema)} == {"ck_preferences_work_modes", "ck_preferences_employment_types"}
    assert {x["name"] for x in inspect(c).get_check_constraints("career_preference_custom_values", schema=schema)} == {"ck_custom_preference_type"}
    assert rows(c) == before
    command.downgrade(cfg, PREVIOUS)
    assert rows(c) == before
    assert inspect(c).get_check_constraints("career_preferences", schema=schema) == []
    command.upgrade(cfg, HEAD)


@pytest.mark.parametrize("values", [{"modes": ["INVALID"]}, {"types": ["FULL_TIME"]}, {"custom_type": "UNKNOWN"}, {"modes": [None]}])
def test_invalid_legacy_fails_without_repair(previous_schema, values):
    c, cfg, schema, owner = previous_schema
    insert(c, owner, **values)
    before = rows(c)
    with pytest.raises(IntegrityError), c.begin_nested():
        command.upgrade(cfg, HEAD)
    assert rows(c) == before
    assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == PREVIOUS
    assert inspect(c).get_check_constraints("career_preferences", schema=schema) == []


@pytest.mark.parametrize("values", [{"modes": ["INVALID"]}, {"types": ["FULL_TIME"]}, {"custom_type": "UNKNOWN"}, {"modes": [None]}])
def test_direct_sql_invalid_choices_rejected(previous_schema, values):
    c, cfg, _, owner = previous_schema
    command.upgrade(cfg, HEAD)
    with pytest.raises(IntegrityError), c.begin_nested():
        insert(c, owner, **values)
