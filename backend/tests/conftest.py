"""Explicit disposable PostgreSQL 16 target; migrations own DDL, tests roll back."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.tests.database_target import validate_test_target

# Runs before application imports bind an engine. Never fall back to DATABASE_URL.
try:
    TEST_URL = validate_test_target(os.environ)
except ValueError as exc:
    raise pytest.UsageError(str(exc)) from exc
os.environ["DATABASE_URL"] = TEST_URL
# Test migrations must not inherit a local direct staging connection from .env.
os.environ["DATABASE_MIGRATION_URL"] = TEST_URL
os.environ["APP_ENV"] = "test"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def database_engine():
    engine = create_engine(TEST_URL)
    with engine.connect() as connection:
        version = int(connection.exec_driver_sql("SHOW server_version_num").scalar_one())
        if not 160000 <= version < 170000:
            pytest.fail("Integration tests require PostgreSQL 16")
    cfg = Config(str(ROOT / "backend/alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_URL.replace("%", "%%"))
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def isolated_database(database_engine, monkeypatch, tmp_path):
    from backend.app.core import unit_of_work
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "STORAGE_LOCAL_ROOT", str(tmp_path / "storage"))
    with database_engine.connect() as connection:
        transaction = connection.begin()
        factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
        monkeypatch.setattr(unit_of_work, "SessionLocal", factory)
        yield connection
        transaction.rollback()
