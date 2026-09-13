"""Fresh transactional PostgreSQL schema and migration/model fidelity checks."""

from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from backend.app.models import Base


def test_fresh_database_migration_to_head(database_engine):
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with database_engine.connect() as connection:
        transaction = connection.begin()
        schema = "migration_" + uuid4().hex
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        assert inspect(connection).get_table_names(schema=schema) == []
        cfg.attributes["connection"] = connection
        try:
            command.upgrade(cfg, "head")
            context = MigrationContext.configure(connection)
            assert context.get_current_heads() == tuple(
                ScriptDirectory.from_config(cfg).get_heads()
            )
            assert set(inspect(connection).get_table_names(schema=schema)) == set(
                Base.metadata.tables
            ) | {"alembic_version"}
            command.downgrade(cfg, "base")
            assert inspect(connection).get_table_names(schema=schema) == ["alembic_version"]
            command.upgrade(cfg, "head")
        finally:
            transaction.rollback()


def test_migrated_schema_matches_models(database_engine):
    with database_engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "compare_server_default": True}
        )
        assert compare_metadata(context, Base.metadata) == []
