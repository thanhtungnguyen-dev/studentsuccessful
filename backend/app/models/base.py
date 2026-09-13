"""Shared PostgreSQL model utilities."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from backend.app.core.database import Base


def generate_uuid() -> UUID:
    """Return a native UUID for PostgreSQL UUID columns."""
    return uuid4()


def utc_now() -> datetime:
    """Return an aware UTC event timestamp."""
    return datetime.now(timezone.utc)


__all__ = ["Base", "generate_uuid", "utc_now"]
