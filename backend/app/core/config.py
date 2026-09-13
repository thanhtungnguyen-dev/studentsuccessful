"""Application configuration loaded from environment variables."""

import re
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Determine project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    APP_NAME: str = "StudentSuccessful"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # PostgreSQL is authoritative in development and integration tests.
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/studentsuccessful"
    # An optional direct/admin PostgreSQL connection used only by Alembic.
    # Application requests and workers always continue to use DATABASE_URL.
    DATABASE_MIGRATION_URL: str | None = None
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 5
    DATABASE_POOL_TIMEOUT_SECONDS: int = 30
    DATABASE_POOL_RECYCLE_SECONDS: int = 1_800
    DATABASE_CONNECT_TIMEOUT_SECONDS: int = 10

    # Server Host & Port
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Session & Security
    # Opaque DB sessions store SHA-256 token hashes in `user_sessions`.
    # CSRF tokens are random 256-bit tokens with SHA-256 stored in `user_sessions`.
    SESSION_COOKIE_NAME: str = "__Host-ss_session"
    SESSION_COOKIE_SECURE: bool = False
    SESSION_EXPIRE_DAYS: int = 14
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    # Storage Adapter (local in development; private S3-compatible storage in production)
    STORAGE_BACKEND: str = "local"
    # Demo/staging-only opt-in for platforms with ephemeral local filesystems.
    ALLOW_EPHEMERAL_LOCAL_STORAGE: bool = False
    STORAGE_LOCAL_ROOT: str = str(PROJECT_ROOT / "data" / "resumes")
    STORAGE_S3_BUCKET: str = ""
    STORAGE_S3_REGION: str = ""
    STORAGE_S3_ENDPOINT_URL: str | None = None
    STORAGE_S3_PREFIX: str = "resumes"

    # A JSON array of public, credential-free ATS board configurations. It is
    # parsed only by the manual live-ingestion command, so a bad operational
    # configuration cannot stop the web application from starting.
    LIVE_JOB_SOURCES_JSON: str = "[]"
    LIVE_JOB_HTTP_TIMEOUT_SECONDS: float = 10.0
    LIVE_COLLECTOR_CONCURRENCY: int = 3
    LIVE_COLLECTOR_MAX_BACKOFF_SECONDS: int = 3600

    # Worker heartbeats make a stopped collector distinguishable from an
    # individual source failure. The lease protects deploy overlap and restart.
    WORKER_LEASE_SECONDS: int = 120
    WORKER_HEARTBEAT_STALE_SECONDS: int = 180

    # Canonical job lifecycle is deliberately conservative: one complete
    # successful absence makes a job stale, while two are needed for closure.
    JOB_NEW_WINDOW_HOURS: int = 72
    JOB_CLOSE_AFTER_SUCCESSFUL_ABSENCES: int = 2

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def migration_database_url(self) -> str:
        """Use a direct migration connection when one is explicitly configured."""
        return self.DATABASE_MIGRATION_URL or self.DATABASE_URL

    @model_validator(mode="after")
    def validate_production_configuration(self) -> "Settings":
        """Enforces fast failure when entering production with insecure or missing configurations."""
        if self.APP_ENV not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        if self.STORAGE_S3_ENDPOINT_URL is not None:
            self.STORAGE_S3_ENDPOINT_URL = self.STORAGE_S3_ENDPOINT_URL.strip() or None
        origin = urlsplit(self.FRONTEND_ORIGIN)
        if (
            origin.scheme not in {"http", "https"}
            or not origin.hostname
            or origin.username is not None
            or origin.password is not None
            or origin.path not in {"", "/"}
            or origin.query
            or origin.fragment
            or "*" in self.FRONTEND_ORIGIN
        ):
            raise ValueError("FRONTEND_ORIGIN must be a single explicit HTTP(S) origin")
        # Browser Origin serialization omits default ports and a trailing slash.
        port = origin.port
        hostname = origin.hostname.lower()
        host = f"[{hostname}]" if ":" in hostname else hostname
        if port is not None and (origin.scheme, port) not in {("http", 80), ("https", 443)}:
            host += f":{port}"
        self.FRONTEND_ORIGIN = f"{origin.scheme}://{host}"

        if not 1 <= self.DATABASE_POOL_SIZE <= 50:
            raise ValueError("DATABASE_POOL_SIZE must be between 1 and 50")
        if not 0 <= self.DATABASE_MAX_OVERFLOW <= 50:
            raise ValueError("DATABASE_MAX_OVERFLOW must be between 0 and 50")
        if not 1 <= self.DATABASE_POOL_TIMEOUT_SECONDS <= 120:
            raise ValueError("DATABASE_POOL_TIMEOUT_SECONDS must be between 1 and 120")
        if not 60 <= self.DATABASE_POOL_RECYCLE_SECONDS <= 86_400:
            raise ValueError("DATABASE_POOL_RECYCLE_SECONDS must be between 60 and 86400")
        if not 1 <= self.DATABASE_CONNECT_TIMEOUT_SECONDS <= 60:
            raise ValueError("DATABASE_CONNECT_TIMEOUT_SECONDS must be between 1 and 60")
        if not 60 <= self.WORKER_LEASE_SECONDS <= 3_600:
            raise ValueError("WORKER_LEASE_SECONDS must be between 60 and 3600")
        if not self.WORKER_LEASE_SECONDS <= self.WORKER_HEARTBEAT_STALE_SECONDS <= 7_200:
            raise ValueError(
                "WORKER_HEARTBEAT_STALE_SECONDS must be at least the worker lease and at most 7200"
            )
        if self.STORAGE_BACKEND not in {"local", "s3"}:
            raise ValueError("STORAGE_BACKEND must be local or s3")
        if self.STORAGE_BACKEND == "s3":
            prefix = PurePosixPath(self.STORAGE_S3_PREFIX)
            if (
                not self.STORAGE_S3_BUCKET
                or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", self.STORAGE_S3_BUCKET)
            ):
                raise ValueError("STORAGE_S3_BUCKET must be a valid bucket name")
            if not self.STORAGE_S3_REGION.strip():
                raise ValueError("STORAGE_S3_REGION is required for S3 storage")
            if (
                not self.STORAGE_S3_PREFIX
                or "\\" in self.STORAGE_S3_PREFIX
                or prefix.is_absolute()
                or any(part in {"", ".", ".."} for part in prefix.parts)
            ):
                raise ValueError("STORAGE_S3_PREFIX must be a safe relative object prefix")
            if self.STORAGE_S3_ENDPOINT_URL:
                endpoint = urlsplit(self.STORAGE_S3_ENDPOINT_URL)
                if (
                    endpoint.scheme not in {"http", "https"}
                    or not endpoint.hostname
                    or endpoint.username is not None
                    or endpoint.password is not None
                    or endpoint.query
                    or endpoint.fragment
                ):
                    raise ValueError("STORAGE_S3_ENDPOINT_URL must be an explicit HTTP(S) endpoint")
        if self.APP_ENV == "production":
            if self.DEBUG:
                raise ValueError("Production requires DEBUG=false")
            if not self.SESSION_COOKIE_SECURE:
                raise ValueError("Production requires SESSION_COOKIE_SECURE=true")
            if self.SESSION_COOKIE_NAME != "__Host-ss_session":
                raise ValueError("Production requires SESSION_COOKIE_NAME=__Host-ss_session")
            if origin.scheme != "https":
                raise ValueError("Production requires an HTTPS FRONTEND_ORIGIN")
            if not self.DATABASE_URL.startswith("postgresql"):
                raise ValueError(
                    "CRITICAL: a production PostgreSQL DATABASE_URL is required."
                )
            if self.STORAGE_BACKEND != "s3" and not (
                self.STORAGE_BACKEND == "local" and self.ALLOW_EPHEMERAL_LOCAL_STORAGE
            ):
                raise ValueError("Production requires private S3-compatible resume storage")
            if self.STORAGE_S3_ENDPOINT_URL and not self.STORAGE_S3_ENDPOINT_URL.startswith("https://"):
                raise ValueError("Production S3 endpoints must use HTTPS")
        return self


settings = Settings()
