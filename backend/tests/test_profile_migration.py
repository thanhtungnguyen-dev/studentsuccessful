"""Existing profile facts survive the narrow contact nullability migration."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


def test_existing_profile_migration_preserves_data_and_allows_optional_clear(database_engine):
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with database_engine.connect() as connection:
        transaction = connection.begin()
        schema = "profile_migration_" + uuid4().hex
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        cfg.attributes["connection"] = connection
        try:
            command.upgrade(cfg, "aba441bbcc36")
            user_id = uuid4()
            connection.execute(text("INSERT INTO users (id, email, password_hash) VALUES (:id, 'migration@example.com', 'test')"), {"id": user_id})
            connection.execute(text("""INSERT INTO application_profiles
                (user_id, legal_first_name, legal_last_name, phone_number, address_city,
                 address_state_province, address_postal_code, address_country_code)
                VALUES (:id, 'Anne', '李', '+1 403 555 0100', 'Calgary', 'Alberta', 'T2P 1J9', 'CA')"""), {"id": user_id})
            before = dict(connection.execute(text("SELECT * FROM application_profiles")).mappings().one())
            command.upgrade(cfg, "b61f0a2c9d34")
            assert dict(connection.execute(text("SELECT * FROM application_profiles")).mappings().one()) == before
            columns = {column["name"]: column for column in inspect(connection).get_columns("application_profiles", schema=schema)}
            optional = ("phone_number", "address_city", "address_state_province", "address_postal_code", "address_country_code")
            assert all(columns[key]["nullable"] for key in optional)
            assert not columns["legal_first_name"]["nullable"]
            assert not columns["legal_last_name"]["nullable"]
            connection.execute(text("UPDATE application_profiles SET phone_number = NULL"))
            with pytest.raises(IntegrityError), connection.begin_nested():
                command.downgrade(cfg, "aba441bbcc36")
            assert connection.execute(text("SELECT phone_number FROM application_profiles")).scalar_one() is None
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "b61f0a2c9d34"
            connection.execute(text("UPDATE application_profiles SET phone_number = '+1 403 555 0100'"))
            command.downgrade(cfg, "aba441bbcc36")
            assert dict(connection.execute(text("SELECT * FROM application_profiles")).mappings().one()) == before
            command.upgrade(cfg, "b61f0a2c9d34")
        finally:
            transaction.rollback()
