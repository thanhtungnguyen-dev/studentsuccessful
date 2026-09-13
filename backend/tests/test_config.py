"""Configuration checks for production host-only cookies and explicit origins."""

import pytest

from backend.app.core.config import Settings


def production(**overrides):
    values = dict(
        APP_ENV="production",
        DEBUG=False,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_NAME="__Host-ss_session",
        FRONTEND_ORIGIN="https://students.example",
        DATABASE_URL="postgresql+psycopg2://localhost/studentsuccessful",
        STORAGE_BACKEND="s3",
        STORAGE_S3_BUCKET="studentsuccessful-private-resumes",
        STORAGE_S3_REGION="us-east-1",
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_configuration_loading_development():
    config = Settings(_env_file=None, APP_ENV="development", SESSION_COOKIE_SECURE=False)
    assert config.APP_NAME == "StudentSuccessful"
    assert config.SESSION_COOKIE_NAME == "__Host-ss_session"
    assert not config.SESSION_COOKIE_SECURE


def test_production_fails_fast_on_insecure_cookies():
    with pytest.raises(ValueError, match="SESSION_COOKIE_SECURE=true"):
        production(SESSION_COOKIE_SECURE=False)


def test_production_requires_host_cookie_name():
    with pytest.raises(ValueError, match="SESSION_COOKIE_NAME=__Host-ss_session"):
        production(SESSION_COOKIE_NAME="ss_session")


def test_production_requires_https_origin():
    with pytest.raises(ValueError, match="HTTPS FRONTEND_ORIGIN"):
        production(FRONTEND_ORIGIN="http://students.example")


def test_production_fails_fast_on_sqlite():
    with pytest.raises(ValueError, match="PostgreSQL DATABASE_URL"):
        production(DATABASE_URL="sqlite:///./data/prod.db")


def test_production_valid_configuration_needs_no_global_secret():
    config = production()
    assert config.SESSION_COOKIE_SECURE
    assert "SESSION_SECRET" not in Settings.model_fields


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.example.org",
        "null",
        "https://example.org/path",
        "https://user:pass@example.org",
        "https://example.org?x=1",
        "https://example.org#fragment",
    ],
)
def test_rejects_ambiguous_frontend_origin(origin):
    with pytest.raises(ValueError, match="explicit HTTP"):
        production(FRONTEND_ORIGIN=origin)


def test_normalizes_configured_origin():
    assert (
        production(FRONTEND_ORIGIN="https://STUDENTS.example:443/").FRONTEND_ORIGIN
        == "https://students.example"
    )


def test_database_default_is_postgresql(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = Settings(_env_file=None)
    assert config.DATABASE_URL.startswith("postgresql+psycopg2://")


def test_migration_database_url_is_optional_and_separate(monkeypatch):
    monkeypatch.delenv("DATABASE_MIGRATION_URL", raising=False)
    config = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+psycopg2://runtime.example/studentsuccessful",
        DATABASE_MIGRATION_URL="postgresql+psycopg2://migration.example/studentsuccessful",
    )
    assert config.DATABASE_URL.endswith("runtime.example/studentsuccessful")
    assert config.migration_database_url.endswith("migration.example/studentsuccessful")
    assert Settings(
        _env_file=None,
        DATABASE_URL="postgresql+psycopg2://runtime.example/studentsuccessful",
    ).migration_database_url.endswith("runtime.example/studentsuccessful")


def test_production_requires_private_s3_storage_and_disabled_debug():
    with pytest.raises(ValueError, match="private S3"):
        production(STORAGE_BACKEND="local")
    with pytest.raises(ValueError, match="DEBUG=false"):
        production(DEBUG=True)


def test_rejects_invalid_production_pool_and_worker_settings():
    with pytest.raises(ValueError, match="DATABASE_POOL_SIZE"):
        production(DATABASE_POOL_SIZE=0)
    with pytest.raises(ValueError, match="HEARTBEAT_STALE"):
        production(WORKER_LEASE_SECONDS=180, WORKER_HEARTBEAT_STALE_SECONDS=120)
