"""One additive migration, no seeds or inference, clean downgrade."""

from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


def test_additive_migration_preserves_factual_skill_and_existing_tables(database_engine):
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with database_engine.connect() as c:
        transaction = c.begin()
        schema = "portfolio_migration_" + uuid4().hex
        c.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        c.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        cfg.attributes["connection"] = c
        try:
            command.upgrade(cfg, "ab6c8fd54793")
            c.execute(
                text(
                    "INSERT INTO users(email,password_hash) VALUES ('existing@example.com','test')"
                )
            )
            c.execute(
                text(
                    "INSERT INTO skills(name,slug,category) VALUES ('Existing','existing','TECHNOLOGY')"
                )
            )
            c.execute(
                text(
                    "INSERT INTO user_skills(user_id,skill_id,source,user_notes) SELECT users.id,skills.id,'USER','Keep' FROM users,skills"
                )
            )
            before = {
                table: list(c.execute(text("SELECT * FROM " + table)).mappings())
                for table in ["users", "skills", "user_skills"]
            }
            tables = set(inspect(c).get_table_names(schema=schema))
            command.upgrade(cfg, "bc7d90e658a4")
            assert set(inspect(c).get_table_names(schema=schema)) - tables == {
                "projects",
                "project_skills",
                "project_custom_skills",
                "user_custom_skills",
            }
            for table in [
                "projects",
                "project_skills",
                "project_custom_skills",
                "user_custom_skills",
            ]:
                assert c.execute(text("SELECT count(*) FROM " + table)).scalar_one() == 0
            assert {
                table: list(c.execute(text("SELECT * FROM " + table)).mappings())
                for table in before
            } == before
            command.downgrade(cfg, "ab6c8fd54793")
            assert set(inspect(c).get_table_names(schema=schema)) == tables
            assert {
                table: list(c.execute(text("SELECT * FROM " + table)).mappings())
                for table in before
            } == before
            command.upgrade(cfg, "bc7d90e658a4")
        finally:
            transaction.rollback()
