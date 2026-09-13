"""Existing users remain incomplete; migration adds and removes only one column."""
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


def test_existing_user_upgrade_and_clean_downgrade(database_engine):
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with database_engine.connect() as connection:
        transaction = connection.begin()
        schema = "onboarding_migration_" + uuid4().hex
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        cfg.attributes["connection"] = connection
        try:
            command.upgrade(cfg, "fa5b7ec43682")
            connection.execute(text("INSERT INTO users(email,password_hash) VALUES ('existing@example.com','test')"))
            before = dict(connection.execute(text("SELECT * FROM users")).mappings().one())
            tables = inspect(connection).get_table_names(schema=schema)
            command.upgrade(cfg, "ab6c8fd54793")
            after = dict(connection.execute(text("SELECT * FROM users")).mappings().one())
            assert after.pop("onboarding_completed_at") is None
            assert after == before
            assert set(inspect(connection).get_table_names(schema=schema)) == set(tables)
            column = next(c for c in inspect(connection).get_columns("users", schema=schema) if c["name"] == "onboarding_completed_at")
            assert column["nullable"] and column["default"] is None and column["type"].timezone
            command.downgrade(cfg, "fa5b7ec43682")
            assert dict(connection.execute(text("SELECT * FROM users")).mappings().one()) == before
            command.upgrade(cfg, "head")
            assert connection.execute(text("SELECT onboarding_completed_at FROM users")).scalar_one() is None
        finally:
            transaction.rollback()
