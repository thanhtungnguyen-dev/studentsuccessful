"""Offline structured observations; no scraping or account acquisition."""

import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.ingestion.dto import ExternalJobDTO, ExternalJobMetadata
from backend.app.ingestion.public_http import public_url

SOURCES = {
    "linkedin": "TRUSTED_STRUCTURED",
    "indeed": "TRUSTED_STRUCTURED",
    "intern_insider": "TRUSTED_AGGREGATOR",
}


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: str
    external_id: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9_.-]+$")
    listing_url: str
    apply_url: str | None = None
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=150)
    location: str | None = Field(default=None, max_length=500)
    employment_type: str = "UNSPECIFIED"
    work_mode: str = "UNSPECIFIED"
    description: str | None = Field(default=None, max_length=20000)
    posted_at: str | None = None
    metadata: ExternalJobMetadata | None = None

    @field_validator("source")
    @classmethod
    def source_known(cls, value):
        if value not in SOURCES:
            raise ValueError("Unknown observation source")
        return value

    @field_validator("listing_url", "apply_url")
    @classmethod
    def safe_url(cls, value):
        if value is None:
            return value
        public_url(value)
        p = urlsplit(value)
        if (
            p.scheme != "https"
            or p.fragment
            or any(
                re.search(
                    r"token|secret|password|api.?key|signature|credential|authorization", key, re.I
                )
                for key, _ in parse_qsl(p.query)
            )
        ):
            raise ValueError("Unsafe observation URL")
        return value

    def dto(self):
        from datetime import datetime

        posted = (
            datetime.fromisoformat(self.posted_at.replace("Z", "+00:00"))
            if self.posted_at
            else None
        )
        if posted is not None and posted.utcoffset() is None:
            raise ValueError(
                "Posted timestamp requires offset; vague dates belong in metadata.posted_text"
            )
        host = urlsplit(self.listing_url).hostname
        if self.source == "linkedin" and host not in {
            "linkedin.com",
            "www.linkedin.com",
            "ca.linkedin.com",
        }:
            raise ValueError("LinkedIn listing hostname mismatch")
        if self.source == "indeed" and host not in {
            "indeed.com",
            "www.indeed.com",
            "ca.indeed.com",
        }:
            raise ValueError("Indeed listing hostname mismatch")
        if self.apply_url:
            from backend.app.ingestion.source_detection import detect_source
            from backend.app.services.source_seeds import canonical_board_url

            config = detect_source(self.apply_url, self.company)
            if config:
                supplied = urlsplit(self.apply_url)
                board = urlsplit(canonical_board_url(config))
                # Queries and provider hostname aliases cannot turn a board into a posting.
                if supplied.path.rstrip("/") == board.path.rstrip("/"):
                    raise ValueError("Apply URL must identify a posting, not a board")
        return ExternalJobDTO(
            adapter_key=self.source,
            external_id=self.external_id,
            source_url=self.listing_url,
            application_url=self.apply_url or self.listing_url,
            company=self.company,
            title=self.title,
            role="Unspecified",
            employment_type=self.employment_type,
            work_mode=self.work_mode,
            description=self.description,
            posted_at=posted,
            locations=(self.location,) if self.location else (),
            metadata=self.metadata,
        )


class StructuredObservationAdapter:
    def __init__(self, source):
        self.key = source
        self.source_authority = SOURCES[source]

    def fetch(self):
        return ()


def load_observations(path):
    path = Path(path)
    if path.stat().st_size > 5 * 1024 * 1024:
        raise ValueError("Observation input exceeds 5 MiB")
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not 1 <= len(rows) <= 250:
        raise ValueError("Expected 1-250 structured observations")
    return tuple(Observation.model_validate(row).dto() for row in rows)
