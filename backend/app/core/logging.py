"""Small structured logging helpers that never serialize request bodies or cookies."""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_SAFE_FIELDS = (
    "event",
    "request_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "worker",
    "attempted",
    "failed",
    "scanned",
    "alerts_created",
    "delivered",
    "suppressed",
    "retried",
)


class JsonFormatter(logging.Formatter):
    """Emit compact searchable records from a fixed allowlist of fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _SAFE_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["error_type"] = record.exc_info[0].__name__
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging() -> None:
    """Configure only the application logger so hosting logs remain platform-owned."""

    logger = logging.getLogger("studentsuccessful")
    if getattr(logger, "_studentsuccessful_configured", False):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger._studentsuccessful_configured = True  # type: ignore[attr-defined]


def current_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str):
    return _request_id.set(value)


def reset_request_id(token) -> None:
    _request_id.reset(token)


__all__ = [
    "JsonFormatter",
    "configure_logging",
    "current_request_id",
    "reset_request_id",
    "set_request_id",
]
