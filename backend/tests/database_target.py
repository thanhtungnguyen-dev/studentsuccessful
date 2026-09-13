"""Fail-closed selection of a disposable integration database."""

import re
from collections.abc import Mapping

from sqlalchemy.engine import make_url


def validate_test_target(environ: Mapping[str, str]) -> str:
    raw = environ.get("TEST_DATABASE_URL", "")
    if environ.get("ALLOW_DISPOSABLE_TEST_DATABASE") != "1" or not raw:
        raise ValueError(
            "Set TEST_DATABASE_URL and ALLOW_DISPOSABLE_TEST_DATABASE=1 explicitly; "
            "the application DATABASE_URL is never a test fallback."
        )
    if environ.get("APP_ENV") == "production":
        raise ValueError("Refusing integration tests in production")
    url = make_url(raw)
    if url.drivername != "postgresql+psycopg2" or not re.fullmatch(
        r"studentsuccessful_test_[a-z0-9_]+", url.database or ""
    ):
        raise ValueError(
            "Tests require PostgreSQL and a dedicated studentsuccessful_test_* database"
        )
    return raw
