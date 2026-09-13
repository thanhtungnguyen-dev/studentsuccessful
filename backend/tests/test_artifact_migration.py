"""One additive migration preserves prior tables and creates no artifacts."""

from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


def test_artifact_migration(database_engine):
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with database_engine.connect() as c:
        tx = c.begin()
        schema = "artifact_migration_" + uuid4().hex
        c.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        c.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        cfg.attributes["connection"] = c
        try:
            command.upgrade(cfg, "bc7d90e658a4")
            c.execute(
                text(
                    "INSERT INTO users(email,password_hash) VALUES ('existing@example.com','test')"
                )
            )
            before = list(c.execute(text("SELECT * FROM users")).mappings())
            tables = set(inspect(c).get_table_names(schema=schema))
            # This historical rollback test ends before the forward-only V2 migration.
            command.upgrade(cfg, "b25c6d4e8f10")
            assert set(inspect(c).get_table_names(schema=schema)) - tables == {
                "career_artifacts",
                "job_source_observations",
                "job_alerts",
                "live_source_states",
                "resume_tailoring_reviews",
                "resume_tailoring_review_items",
                "saved_job_searches",
                "user_job_states",
                "worker_heartbeats",
            }
            assert c.execute(text("SELECT count(*) FROM career_artifacts")).scalar_one() == 0
            assert list(c.execute(text("SELECT * FROM users")).mappings()) == before
            command.downgrade(cfg, "bc7d90e658a4")
            assert set(inspect(c).get_table_names(schema=schema)) == tables
            assert list(c.execute(text("SELECT * FROM users")).mappings()) == before
            # This historical rollback test ends before the forward-only V2 migration.
            command.upgrade(cfg, "b25c6d4e8f10")
        finally:
            tx.rollback()
