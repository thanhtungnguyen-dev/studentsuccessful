"""Public, read-only ATS adapters for configured live job boards.

The adapters deliberately return only :class:`ExternalJobDTO` instances. They
never receive a database session, never submit applications, and keep provider
payloads outside the persistence boundary.
"""

from __future__ import annotations

import ipaddress
import json
import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import quote, urlsplit

import httpx
from pydantic import ConfigDict, Field, ValidationError, field_validator, model_validator

from backend.app.ingestion.dto import ExternalJobDTO
from backend.app.ingestion.public_http import public_get
from backend.app.schemas.common import StrictBaseModel
from backend.app.services.job_ingestion import (
    JobIngestionValidationError,
    normalize_company_identity,
)


class LiveSourceConfigurationError(ValueError):
    """A locally configured source is incomplete or unsafe."""


class LiveSourceFetchError(RuntimeError):
    """A whole public source could not be fetched or parsed as JSON."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "FETCH",
        status_code: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


class LiveSourceRecordError(ValueError):
    """One provider job record is malformed and can be safely skipped."""


_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,49}")
_BOARD_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
_HOSTNAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?")
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_MAX_RETRY_AFTER_SECONDS = 86_400
LIVE_SOURCE_FAMILIES = (
    "greenhouse",
    "lever",
    "ashby",
    "smartrecruiters",
    "rss",
    "recruitee",
    "personio",
    "jsonld",
)


@dataclass(frozen=True)
class LiveFetchResult:
    """One bounded provider response without retaining raw provider payloads."""

    records: tuple[ExternalJobDTO, ...]
    fetched_records: int
    skipped_records: int
    filtered_records: int
    not_modified: bool
    http_status: int | None
    etag: str | None
    last_modified: str | None
    complete_listing: bool


class _SourceNotModified(RuntimeError):
    """Internal control flow for a standards-compliant conditional GET response."""


def _compact_config_text(value: str, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    normalized = " ".join(value.split())
    if not normalized or _CONTROL.search(value) or len(normalized) > maximum:
        raise ValueError(f"{field} is invalid")
    return normalized


def _public_host(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    normalized = value.strip().casefold().rstrip(".")
    if (
        not normalized
        or len(normalized) > 253
        or _CONTROL.search(value)
        or not _HOSTNAME.fullmatch(normalized)
        or normalized in {"localhost", "localhost.localdomain"}
        or normalized.endswith(".localhost")
        or normalized.endswith(".local")
    ):
        raise ValueError(f"{field} must be a public hostname")
    try:
        ipaddress.ip_address(normalized)
    except ValueError:
        return normalized
    raise ValueError(f"{field} must not be an IP address")


def _public_https_url(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or _CONTROL.search(value)
        or any(character.isspace() for character in value)
        or "\\" in value
    ):
        raise ValueError(f"{field} must be a safe public HTTPS URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError(f"{field} must be a safe public HTTPS URL")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{field} has an invalid URL port") from exc
    if port not in {None, 443}:
        raise ValueError(f"{field} must use the default HTTPS port")
    _public_host(parsed.hostname, field)
    return value


class LiveJobSourceConfig(StrictBaseModel):
    """A strict, credential-free configuration for one bounded public source."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    key: str
    family: Literal[
        "greenhouse", "lever", "ashby", "smartrecruiters", "rss", "recruitee", "personio", "jsonld"
    ]
    company: str
    role: str = "Unspecified"
    enabled: bool = True
    max_postings: int = Field(default=100, ge=1, le=250)
    poll_interval_seconds: int | None = Field(default=None, ge=300, le=86_400)
    request_timeout_seconds: float | None = Field(default=None, gt=0, le=60)
    polling_tier: Literal["high", "normal", "low"] = "normal"
    source_authority: (
        Literal[
            "OFFICIAL_COMPANY",
            "OFFICIAL_ATS",
            "TRUSTED_STRUCTURED",
            "TRUSTED_AGGREGATOR",
        ]
        | None
    ) = None
    public_board_url: str | None = None
    board_token: str | None = None
    site: str | None = None
    job_board: str | None = None
    company_identifier: str | None = None
    feed_url: str | None = None
    allowed_job_hosts: list[str] = Field(default_factory=list, max_length=20)
    region: Literal["global", "eu"] = "global"

    @field_validator("key")
    @classmethod
    def safe_key(cls, value: str) -> str:
        if not isinstance(value, str) or not _KEY.fullmatch(value):
            raise ValueError("key must be a safe 1-50 character adapter key")
        return value

    @field_validator("company")
    @classmethod
    def configured_company(cls, value: str) -> str:
        try:
            return normalize_company_identity(value)
        except JobIngestionValidationError as exc:
            raise ValueError("company is invalid") from exc

    @field_validator("role")
    @classmethod
    def configured_role(cls, value: str) -> str:
        return _compact_config_text(value, "role", 100)

    @field_validator("board_token", "site", "job_board", "company_identifier")
    @classmethod
    def safe_board_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not _BOARD_IDENTIFIER.fullmatch(value):
            raise ValueError("board identifier must contain only letters, digits, underscores, or hyphens")
        return value

    @field_validator("feed_url", "public_board_url")
    @classmethod
    def safe_feed_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _public_https_url(value, "feed_url")

    @field_validator("allowed_job_hosts")
    @classmethod
    def safe_allowed_job_hosts(cls, value: list[str]) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("allowed_job_hosts must be a JSON list")
        hosts = [_public_host(host, "allowed_job_hosts entry") for host in value]
        if len(set(hosts)) != len(hosts):
            raise ValueError("allowed_job_hosts must not contain duplicates")
        return hosts

    @model_validator(mode="after")
    def family_requirements(self) -> LiveJobSourceConfig:
        identifiers = {
            "greenhouse": self.board_token,
            "lever": self.site,
            "ashby": self.job_board,
            "smartrecruiters": self.company_identifier,
            "rss": self.feed_url,
            "recruitee": self.public_board_url,
            "personio": self.public_board_url,
            "jsonld": self.public_board_url,
        }
        required = identifiers[self.family]
        if required is None:
            raise ValueError(f"{self.family} requires its configured board identifier")
        unexpected = [
            name
            for name, value in identifiers.items()
            if name != self.family
            and value is not None
            and not (
                name in {"recruitee", "personio", "jsonld"}
                and self.family in {"recruitee", "personio", "jsonld"}
            )
        ]
        if unexpected:
            raise ValueError(
                "source configuration contains another family's board identifier"
            )
        if self.public_board_url and self.family in {"recruitee", "personio"}:
            host = urlsplit(self.public_board_url).hostname or ""
            suffixes = (
                (".recruitee.com",)
                if self.family == "recruitee"
                else (".jobs.personio.de", ".jobs.personio.com")
            )
            if not any(
                host.endswith(suffix) and "." not in host[: -len(suffix)] for suffix in suffixes
            ):
                raise ValueError("Invalid provider board hostname")
        if self.family != "lever" and self.region != "global":
            raise ValueError("only Lever supports the eu region setting")
        if self.family != "rss" and self.allowed_job_hosts:
            raise ValueError("allowed_job_hosts is only supported by rss sources")
        if self.family == "smartrecruiters" and self.max_postings > 50:
            raise ValueError("smartrecruiters max_postings must not exceed 50")
        return self

    @property
    def collection_method(self) -> str:
        return "RSS_ATOM" if self.family == "rss" else "PUBLIC_JSON_API"

    @property
    def source_category(self) -> str:
        return "STRUCTURED_FEED" if self.family == "rss" else "ATS"

    @property
    def effective_source_authority(self) -> str:
        if self.source_authority is not None:
            return self.source_authority
        return "TRUSTED_STRUCTURED" if self.family in {"rss", "jsonld"} else "OFFICIAL_ATS"

    @property
    def permitted_job_hosts(self) -> tuple[str, ...]:
        if self.feed_url is None:
            return ()
        feed_host = _public_host(urlsplit(self.feed_url).hostname or "", "feed_url")
        return (feed_host, *self.allowed_job_hosts)


def load_live_source_configs(value: str) -> tuple[LiveJobSourceConfig, ...]:
    """Parse the environment JSON without making app startup depend on it."""

    if not isinstance(value, str):
        raise LiveSourceConfigurationError("LIVE_JOB_SOURCES_JSON must be JSON text")
    if not value.strip():
        return ()
    try:
        raw = json.loads(value)
    except json.JSONDecodeError as exc:
        raise LiveSourceConfigurationError("LIVE_JOB_SOURCES_JSON must contain valid JSON") from exc
    if not isinstance(raw, list):
        raise LiveSourceConfigurationError("LIVE_JOB_SOURCES_JSON must be a JSON array")

    configs: list[LiveJobSourceConfig] = []
    keys: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise LiveSourceConfigurationError("every live source configuration must be an object")
        try:
            config = LiveJobSourceConfig.model_validate(item)
        except ValidationError as exc:
            raise LiveSourceConfigurationError("a live source configuration is invalid") from exc
        if config.key in keys:
            raise LiveSourceConfigurationError(f"duplicate live source key: {config.key}")
        keys.add(config.key)
        configs.append(config)
    return tuple(configs)


class _HtmlText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"br", "li", "p", "div", "section", "tr", "h1", "h2", "h3"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"li", "p", "div", "section", "tr", "h1", "h2", "h3"}:
            self.parts.append(" ")


def _html_to_text(value: str) -> str:
    parser = _HtmlText()
    parser.feed(value)
    parser.close()
    return " ".join(unescape("".join(parser.parts)).split())


def _object(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise LiveSourceRecordError(f"{field} must be an object")
    return value


def _required_text(record: dict[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str):
        raise LiveSourceRecordError(f"{field} is required text")
    normalized = value.strip()
    if not normalized:
        raise LiveSourceRecordError(f"{field} must not be blank")
    return normalized


def _optional_text(record: dict[str, object], field: str) -> str | None:
    value = record.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise LiveSourceRecordError(f"{field} must be text when supplied")
    normalized = value.strip()
    return normalized or None


def _external_id(record: dict[str, object], *fields: str) -> str:
    for field in fields:
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
    raise LiveSourceRecordError("provider record has no external job ID")


def _timestamp_value(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise LiveSourceRecordError(f"{field} must be an ISO timestamp when supplied")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise LiveSourceRecordError(f"{field} must be an ISO timestamp when supplied") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveSourceRecordError(f"{field} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _timestamp(record: dict[str, object], field: str) -> datetime | None:
    return _timestamp_value(record.get(field), field)


def _feed_timestamp(value: str | None, field: str) -> datetime | None:
    if value is None:
        return None
    try:
        return _timestamp_value(value, field)
    except LiveSourceRecordError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError, OverflowError) as exc:
            raise LiveSourceRecordError(f"{field} must be a timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise LiveSourceRecordError(f"{field} must include a UTC offset")
        return parsed.astimezone(timezone.utc)


def _safe_response_header(value: str | None) -> str | None:
    """Retain only bounded, printable cache validators from a public response."""

    if value is None:
        return None
    normalized = value.strip()
    if not normalized or _CONTROL.search(normalized) or len(normalized) > 255:
        return None
    return normalized


def _retry_after_seconds(value: str | None) -> int | None:
    """Parse a bounded HTTP Retry-After value without trusting arbitrary headers."""

    normalized = _safe_response_header(value)
    if normalized is None:
        return None
    if normalized.isdecimal():
        return min(int(normalized), _MAX_RETRY_AFTER_SECONDS)
    try:
        parsed = parsedate_to_datetime(normalized)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    seconds = int((parsed.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds())
    return min(max(seconds, 0), _MAX_RETRY_AFTER_SECONDS)


def _description(record: dict[str, object], plain_field: str, html_field: str) -> str | None:
    plain = _optional_text(record, plain_field)
    if plain is not None:
        return " ".join(plain.split())
    html = _optional_text(record, html_field)
    return _html_to_text(html) if html is not None else None


def _html_description(record: dict[str, object], field: str) -> str | None:
    value = _optional_text(record, field)
    return _html_to_text(value) if value is not None else None


def _deduplicated_locations(values: list[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(value.split())
        if not normalized:
            continue
        identity = normalized.casefold()
        if identity not in seen:
            result.append(normalized)
            seen.add(identity)
    return tuple(result)


def _work_mode(value: str | None) -> str:
    if value is None:
        return "UNSPECIFIED"
    normalized = re.sub(r"[\s_-]+", "", value).casefold()
    return {
        "remote": "REMOTE",
        "hybrid": "HYBRID",
        "onsite": "ON_SITE",
    }.get(normalized, "UNSPECIFIED")


def _employment_type(value: str | None) -> str:
    if value is None:
        return "UNSPECIFIED"
    normalized = re.sub(r"[\s_-]+", "", value).casefold()
    return {
        "fulltime": "FULL_TIME",
        "parttime": "PART_TIME",
        "intern": "INTERNSHIP",
        "internship": "INTERNSHIP",
        "coop": "CO_OP",
        "contract": "CONTRACT",
        "newgrad": "NEW_GRAD",
        "newgraduate": "NEW_GRAD",
    }.get(normalized, "UNSPECIFIED")


class LiveSourceAdapter:
    """Shared public-JSON fetch and record-isolation behavior."""

    family: str

    def __init__(
        self,
        config: LiveJobSourceConfig,
        *,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self.key = config.key
        self._timeout_seconds = timeout_seconds
        self._client = client
        self.evidence_pages: list[dict] = []
        self._evidence_bytes = 0
        self.evidence_truncated = False
        self.fetched_records = 0
        self.skipped_records = 0
        self.filtered_records = 0
        self._conditional_etag: str | None = None
        self._conditional_last_modified: str | None = None
        self._conditional_request_pending = False
        self._last_http_status: int | None = None
        self._last_etag: str | None = None
        self._last_modified: str | None = None

    @property
    def source_authority(self) -> str:
        return self.config.effective_source_authority

    def _get_response_content(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        accept: str,
        track_response_metadata: bool = True,
    ) -> bytes:
        client = self._client
        headers = {"Accept": accept}
        if self._conditional_request_pending:
            self._conditional_request_pending = False
            if self._conditional_etag is not None:
                headers["If-None-Match"] = self._conditional_etag
            if self._conditional_last_modified is not None:
                headers["If-Modified-Since"] = self._conditional_last_modified
        try:
            if client is not None:
                response = client.get(url, params=params, headers=headers)
            else:
                target = str(httpx.URL(url, params=params)) if params else url
                response = public_get(
                    target, timeout=self._timeout_seconds, headers=headers, redirects=0
                )
        except httpx.TimeoutException as exc:
            raise LiveSourceFetchError(
                "public source request timed out", category="TIMEOUT"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise LiveSourceFetchError("public source request failed", category="NETWORK") from exc
        if track_response_metadata:
            self._last_http_status = response.status_code
            self._last_etag = _safe_response_header(response.headers.get("ETag"))
            self._last_modified = _safe_response_header(response.headers.get("Last-Modified"))
        if response.status_code == 304:
            raise _SourceNotModified
        if response.status_code != 200:
            if response.status_code == 429:
                category = "RATE_LIMITED"
            elif 500 <= response.status_code <= 599:
                category = "HTTP_5XX"
            else:
                category = "HTTP_ERROR"
            raise LiveSourceFetchError(
                f"public source returned HTTP {response.status_code}",
                category=category,
                status_code=response.status_code,
                retry_after_seconds=_retry_after_seconds(response.headers.get("Retry-After")),
            )
        if len(response.content) > _MAX_RESPONSE_BYTES:
            raise LiveSourceFetchError(
                "public source response is too large",
                category="OVERSIZED_RESPONSE",
                status_code=response.status_code,
            )
        self._evidence_bytes += len(response.content)
        if self._evidence_bytes > 8 * 1024 * 1024 or len(self.evidence_pages) >= 52:
            self.evidence_truncated = True
            self.evidence_pages.clear()
        if not self.evidence_truncated:
            self.evidence_pages.append(
                {
                    "url": str(response.request.url),
                    "content": response.text,
                    "status": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                }
            )
        return response.content

    def _get_json(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        track_response_metadata: bool = True,
    ) -> object:
        content = self._get_response_content(
            url,
            params=params,
            accept="application/json",
            track_response_metadata=track_response_metadata,
        )
        try:
            return json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise LiveSourceFetchError(
                "public source returned malformed JSON",
                category="MALFORMED_RESPONSE",
                status_code=self._last_http_status,
            ) from exc

    def _get_xml(self, url: str) -> ElementTree.Element:
        content = self._get_response_content(
            url,
            accept="application/rss+xml, application/atom+xml, application/xml, text/xml",
        )
        if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
            raise LiveSourceFetchError(
                "public feed contains an unsafe XML declaration",
                category="MALFORMED_RESPONSE",
                status_code=self._last_http_status,
            )
        try:
            return ElementTree.fromstring(content)
        except ElementTree.ParseError as exc:
            raise LiveSourceFetchError(
                "public feed returned malformed XML",
                category="MALFORMED_RESPONSE",
                status_code=self._last_http_status,
            ) from exc

    def _build_dto(
        self,
        *,
        external_id: str,
        source_url: str,
        application_url: str,
        title: str,
        description: str | None,
        posted_at: datetime | None = None,
        source_updated_at: datetime | None = None,
        locations: tuple[str, ...] = (),
        employment_type: str = "UNSPECIFIED",
        work_mode: str = "UNSPECIFIED",
        source_status: Literal["ACTIVE", "CLOSED"] = "ACTIVE",
    ) -> ExternalJobDTO:
        from backend.app.ingestion.normalization import title_facts

        inferred_role, inferred_employment, inferred_level = title_facts(title)
        return ExternalJobDTO(
            adapter_key=self.key,
            external_id=external_id,
            source_url=source_url,
            application_url=application_url,
            company=self.config.company,
            title=title,
            role=(inferred_role or self.config.role)
            if self.config.role == "Unspecified"
            else self.config.role,
            employment_type=inferred_employment
            if employment_type == "UNSPECIFIED"
            else employment_type,
            career_level=inferred_level,
            work_mode=work_mode,
            description=description,
            posted_at=posted_at,
            source_updated_at=source_updated_at,
            locations=locations,
            source_status=source_status,
        )

    def fetch_with_metadata(
        self,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> LiveFetchResult:
        """Fetch once, using public cache validators only when a source supplied them."""

        self.evidence_pages: list[dict] = []
        self._evidence_bytes = 0
        self.evidence_truncated = False
        self.fetched_records = 0
        self.skipped_records = 0
        self.filtered_records = 0
        self._conditional_etag = _safe_response_header(etag)
        self._conditional_last_modified = _safe_response_header(last_modified)
        self._conditional_request_pending = bool(
            self._conditional_etag is not None or self._conditional_last_modified is not None
        )
        self._last_http_status = None
        self._last_etag = None
        self._last_modified = None
        output: list[ExternalJobDTO] = []
        try:
            source_records = self._records()
        except _SourceNotModified:
            return LiveFetchResult(
                records=(),
                fetched_records=0,
                skipped_records=0,
                filtered_records=0,
                not_modified=True,
                http_status=self._last_http_status,
                etag=self._last_etag,
                last_modified=self._last_modified,
                complete_listing=False,
            )
        complete_listing = len(source_records) < self.config.max_postings
        for raw in source_records[: self.config.max_postings]:
            self.fetched_records += 1
            try:
                dto = self._parse_record(raw)
            except (JobIngestionValidationError, LiveSourceRecordError, ValidationError):
                self.skipped_records += 1
                continue
            if dto is None:
                self.filtered_records += 1
                continue
            output.append(dto)
        return LiveFetchResult(
            records=tuple(output),
            fetched_records=self.fetched_records,
            skipped_records=self.skipped_records,
            filtered_records=self.filtered_records,
            not_modified=False,
            http_status=self._last_http_status,
            etag=self._last_etag,
            last_modified=self._last_modified,
            complete_listing=complete_listing,
        )

    def fetch(self) -> tuple[ExternalJobDTO, ...]:
        """Backward-compatible Phase 18 fetch interface."""

        return self.fetch_with_metadata().records

    def _records(self) -> list[object]:
        raise NotImplementedError

    def _parse_record(self, raw: object) -> ExternalJobDTO | None:
        raise NotImplementedError


class GreenhouseAdapter(LiveSourceAdapter):
    family = "greenhouse"

    def _records(self) -> list[object]:
        assert self.config.board_token is not None
        payload = self._get_json(
            "https://boards-api.greenhouse.io/v1/boards/"
            + quote(self.config.board_token, safe="")
            + "/jobs",
            params={"content": "true"},
        )
        data = _object(payload, "Greenhouse response")
        jobs = data.get("jobs")
        if not isinstance(jobs, list):
            raise LiveSourceFetchError("Greenhouse response has no jobs list")
        return jobs

    def _parse_record(self, raw: object) -> ExternalJobDTO:
        record = _object(raw, "Greenhouse job")
        locations: list[str] = []
        location = record.get("location")
        if location is not None:
            location_data = _object(location, "Greenhouse location")
            name = _optional_text(location_data, "name")
            if name is not None:
                locations.append(name)
        offices = record.get("offices")
        if offices is not None:
            if not isinstance(offices, list):
                raise LiveSourceRecordError("Greenhouse offices must be a list")
            for office in offices:
                office_data = _object(office, "Greenhouse office")
                value = _optional_text(office_data, "location")
                if value is not None:
                    locations.append(value)
        source_url = _required_text(record, "absolute_url")
        return self._build_dto(
            external_id=_external_id(record, "id"),
            source_url=source_url,
            application_url=source_url,
            title=_required_text(record, "title"),
            description=_html_description(record, "content"),
            posted_at=_timestamp(record, "first_published"),
            source_updated_at=_timestamp(record, "updated_at"),
            locations=_deduplicated_locations(locations),
        )


class LeverAdapter(LiveSourceAdapter):
    family = "lever"

    def _records(self) -> list[object]:
        assert self.config.site is not None
        base = "https://api.eu.lever.co" if self.config.region == "eu" else "https://api.lever.co"
        endpoint = base + "/v0/postings/" + quote(self.config.site, safe="")
        result: list[object] = []
        skip = 0
        while len(result) < self.config.max_postings:
            limit = min(100, self.config.max_postings - len(result))
            page = self._get_json(endpoint, params={"mode": "json", "skip": skip, "limit": limit})
            if not isinstance(page, list):
                raise LiveSourceFetchError("Lever response must be a jobs list")
            result.extend(page)
            if len(page) < limit:
                break
            skip += len(page)
        return result

    def _parse_record(self, raw: object) -> ExternalJobDTO:
        record = _object(raw, "Lever job")
        categories = record.get("categories")
        if categories is None:
            category_data: dict[str, object] = {}
        else:
            category_data = _object(categories, "Lever categories")
        locations: list[str] = []
        primary_location = _optional_text(category_data, "location")
        if primary_location is not None:
            locations.append(primary_location)
        all_locations = category_data.get("allLocations")
        if all_locations is not None:
            if not isinstance(all_locations, list):
                raise LiveSourceRecordError("Lever allLocations must be a list")
            for value in all_locations:
                if not isinstance(value, str):
                    raise LiveSourceRecordError("Lever allLocations entries must be text")
                locations.append(value)
        source_url = _required_text(record, "hostedUrl")
        application_url = _optional_text(record, "applyUrl") or source_url
        return self._build_dto(
            external_id=_external_id(record, "id"),
            source_url=source_url,
            application_url=application_url,
            title=_required_text(record, "text"),
            description=_description(record, "descriptionPlain", "description"),
            locations=_deduplicated_locations(locations),
            employment_type=_employment_type(_optional_text(category_data, "commitment")),
            work_mode=_work_mode(_optional_text(record, "workplaceType")),
        )


class AshbyAdapter(LiveSourceAdapter):
    family = "ashby"

    def _records(self) -> list[object]:
        assert self.config.job_board is not None
        payload = self._get_json(
            "https://api.ashbyhq.com/posting-api/job-board/"
            + quote(self.config.job_board, safe=""),
        )
        data = _object(payload, "Ashby response")
        jobs = data.get("jobs")
        if not isinstance(jobs, list):
            raise LiveSourceFetchError("Ashby response has no jobs list")
        return jobs

    def _parse_record(self, raw: object) -> ExternalJobDTO | None:
        record = _object(raw, "Ashby job")
        listed = record.get("isListed")
        if listed is False:
            return None
        if listed is not None and not isinstance(listed, bool):
            raise LiveSourceRecordError("Ashby isListed must be boolean")
        locations: list[str] = []
        primary_location = _optional_text(record, "location")
        if primary_location is not None:
            locations.append(primary_location)
        secondary_locations = record.get("secondaryLocations")
        if secondary_locations is not None:
            if not isinstance(secondary_locations, list):
                raise LiveSourceRecordError("Ashby secondaryLocations must be a list")
            for location in secondary_locations:
                location_data = _object(location, "Ashby secondary location")
                value = _optional_text(location_data, "location")
                if value is not None:
                    locations.append(value)
        source_url = _required_text(record, "jobUrl")
        application_url = _optional_text(record, "applyUrl") or source_url
        workplace = _optional_text(record, "workplaceType")
        is_remote = record.get("isRemote")
        if is_remote is not None and not isinstance(is_remote, bool):
            raise LiveSourceRecordError("Ashby isRemote must be boolean")
        work_mode = _work_mode(workplace)
        if work_mode == "UNSPECIFIED" and is_remote is True:
            work_mode = "REMOTE"
        return self._build_dto(
            external_id=_external_id(record, "id", "jobPostingId", "jobId"),
            source_url=source_url,
            application_url=application_url,
            title=_required_text(record, "title"),
            description=_description(record, "descriptionPlain", "descriptionHtml"),
            posted_at=_timestamp(record, "publishedAt"),
            locations=_deduplicated_locations(locations),
            employment_type=_employment_type(_optional_text(record, "employmentType")),
            work_mode=work_mode,
        )


class SmartRecruitersAdapter(LiveSourceAdapter):
    """Bounded, public Posting API collection for one configured company."""

    family = "smartrecruiters"

    def _records(self) -> list[object]:
        assert self.config.company_identifier is not None
        endpoint = (
            "https://api.smartrecruiters.com/v1/companies/"
            + quote(self.config.company_identifier, safe="")
            + "/postings"
        )
        listing: list[object] = []
        offset = 0
        while len(listing) < self.config.max_postings:
            # Keep each public page and the associated optional detail fan-out
            # small. The source cap remains 50 records per cycle.
            limit = min(25, self.config.max_postings - len(listing))
            payload = self._get_json(
                endpoint,
                params={"destination": "PUBLIC", "limit": limit, "offset": offset},
            )
            data = _object(payload, "SmartRecruiters response")
            page = data.get("content")
            if not isinstance(page, list):
                raise LiveSourceFetchError("SmartRecruiters response has no content list")
            listing.extend(page)
            if len(page) < limit:
                break
            offset += len(page)

        resolved: list[object] = []
        for raw in listing:
            if not isinstance(raw, dict):
                resolved.append(raw)
                continue
            # Detail responses carry the official Posting and Apply destinations
            # when a compact list result does not. Never fetch arbitrary URLs:
            # the endpoint remains the configured provider/board identity.
            has_public_url = any(
                isinstance(raw.get(field), str) and raw[field].strip()
                for field in ("postingUrl", "applyUrl")
            )
            if has_public_url:
                resolved.append(raw)
                continue
            try:
                external_id = _external_id(raw, "id", "uuid")
                detail = self._get_json(
                    endpoint + "/" + quote(external_id, safe=""),
                    track_response_metadata=False,
                )
                detail_data = _object(detail, "SmartRecruiters posting details")
            except LiveSourceRecordError:
                resolved.append(raw)
                continue
            except LiveSourceFetchError as exc:
                # A provider can remove one posting between list and detail
                # calls. Isolate only malformed/ordinary per-record responses;
                # rate limiting and provider outages remain source failures.
                if exc.category in {"HTTP_ERROR", "MALFORMED_RESPONSE", "OVERSIZED_RESPONSE"}:
                    resolved.append(raw)
                    continue
                raise
            merged = dict(raw)
            merged.update(detail_data)
            resolved.append(merged)
        return resolved

    def _parse_record(self, raw: object) -> ExternalJobDTO:
        record = _object(raw, "SmartRecruiters job")
        active = record.get("active")
        if active is not None and not isinstance(active, bool):
            raise LiveSourceRecordError("SmartRecruiters active must be boolean")

        locations: list[str] = []
        work_mode = "UNSPECIFIED"
        location = record.get("location")
        if location is not None:
            location_data = _object(location, "SmartRecruiters location")
            parts = [
                _optional_text(location_data, "city"),
                _optional_text(location_data, "region"),
                _optional_text(location_data, "country"),
            ]
            location_text = ", ".join(value for value in parts if value is not None)
            if location_text:
                locations.append(location_text)
            remote = location_data.get("remote")
            if remote is not None and not isinstance(remote, bool):
                raise LiveSourceRecordError("SmartRecruiters location remote must be boolean")
            if remote is True:
                work_mode = "REMOTE"

        employment = record.get("typeOfEmployment")
        employment_data = {} if employment is None else _object(employment, "SmartRecruiters type")
        source_url = _optional_text(record, "postingUrl")
        application_url = _optional_text(record, "applyUrl")
        if source_url is None and application_url is None:
            raise LiveSourceRecordError("SmartRecruiters job has no public posting URL")
        source_url = source_url or application_url
        assert source_url is not None
        description = _smartrecruiters_description(record)
        updated_at = (
            _timestamp(record, "updatedAt")
            if record.get("updatedAt") is not None
            else _timestamp(record, "lastUpdatedDate")
        )
        return self._build_dto(
            external_id=_external_id(record, "id", "uuid"),
            source_url=source_url,
            application_url=application_url or source_url,
            title=_required_text(record, "name"),
            description=description,
            posted_at=_timestamp(record, "releasedDate"),
            source_updated_at=updated_at,
            locations=_deduplicated_locations(locations),
            employment_type=_employment_type(_optional_text(employment_data, "label")),
            work_mode=work_mode,
            source_status="CLOSED" if active is False else "ACTIVE",
        )


def _smartrecruiters_description(record: dict[str, object]) -> str | None:
    job_ad = record.get("jobAd")
    if job_ad is None:
        return None
    job_ad_data = _object(job_ad, "SmartRecruiters job ad")
    sections = job_ad_data.get("sections")
    if sections is None:
        return None
    sections_data = _object(sections, "SmartRecruiters job ad sections")
    values: list[str] = []
    for field in (
        "jobDescription",
        "qualifications",
        "additionalInformation",
        "companyDescription",
    ):
        section = sections_data.get(field)
        if section is None:
            continue
        section_data = _object(section, f"SmartRecruiters {field}")
        text_value = _optional_text(section_data, "text")
        if text_value is not None:
            values.append(_html_to_text(text_value))
    result = " ".join(value for value in values if value)
    return result or None


def _xml_local_name(value: object) -> str:
    return value.rsplit("}", 1)[-1].casefold() if isinstance(value, str) else ""


def _xml_text(element: ElementTree.Element, *names: str) -> str | None:
    wanted = {name.casefold() for name in names}
    for child in element:
        if _xml_local_name(child.tag) not in wanted:
            continue
        value = " ".join("".join(child.itertext()).split())
        if value:
            return value
    return None


def _xml_link(
    element: ElementTree.Element,
    *,
    relations: set[str],
) -> str | None:
    for child in element:
        if _xml_local_name(child.tag) != "link":
            continue
        relation = child.attrib.get("rel", "alternate").casefold()
        if relation not in relations:
            continue
        value = child.attrib.get("href") or " ".join("".join(child.itertext()).split())
        if value:
            return value
    return None


def _xml_category(element: ElementTree.Element) -> str | None:
    for child in element:
        if _xml_local_name(child.tag) != "category":
            continue
        value = child.attrib.get("term") or " ".join("".join(child.itertext()).split())
        if value:
            return value
    return None


def _feed_record(element: ElementTree.Element, *, atom: bool) -> dict[str, object]:
    source_url = _xml_link(element, relations={"", "alternate"})
    if not atom:
        source_url = _xml_text(element, "link") or source_url
    application_url = _xml_link(element, relations={"apply", "application"})
    if application_url is None:
        application_url = _xml_text(element, "applyurl", "applicationurl")
    employment = _xml_text(element, "employmenttype", "jobtype")
    if employment is None:
        employment = _xml_category(element)
    status = (_xml_text(element, "status") or "").casefold()
    return {
        "external_id": _xml_text(element, "id" if atom else "guid"),
        "title": _xml_text(element, "title"),
        "source_url": source_url,
        "application_url": application_url,
        "description": _xml_text(element, "content", "summary", "description"),
        "posted_at": _xml_text(element, "published" if atom else "pubdate"),
        "source_updated_at": _xml_text(element, "updated", "lastbuilddate"),
        "location": _xml_text(element, "location", "joblocation"),
        "employment_type": employment,
        "source_status": "CLOSED" if status in {"closed", "inactive", "expired"} else "ACTIVE",
    }


class RssFeedAdapter(LiveSourceAdapter):
    """One bounded configured public RSS or Atom feed; no link traversal."""

    family = "rss"

    def _records(self) -> list[object]:
        assert self.config.feed_url is not None
        root = self._get_xml(self.config.feed_url)
        root_name = _xml_local_name(root.tag)
        if root_name == "rss":
            channel = next(
                (child for child in root if _xml_local_name(child.tag) == "channel"),
                None,
            )
            if channel is None:
                raise LiveSourceFetchError("RSS feed has no channel", category="MALFORMED_RESPONSE")
            return [
                _feed_record(item, atom=False)
                for item in channel
                if _xml_local_name(item.tag) == "item"
            ]
        if root_name == "feed":
            return [
                _feed_record(entry, atom=True)
                for entry in root
                if _xml_local_name(entry.tag) == "entry"
            ]
        raise LiveSourceFetchError("public feed is not RSS or Atom", category="MALFORMED_RESPONSE")

    def _parse_record(self, raw: object) -> ExternalJobDTO:
        record = _object(raw, "feed item")
        source_url = _required_text(record, "source_url")
        self._require_permitted_job_url(source_url)
        application_url = _optional_text(record, "application_url") or source_url
        self._require_permitted_job_url(application_url)
        location = _optional_text(record, "location")
        return self._build_dto(
            external_id=_external_id(record, "external_id"),
            source_url=source_url,
            application_url=application_url,
            title=_required_text(record, "title"),
            description=_feed_description(_optional_text(record, "description")),
            posted_at=_feed_timestamp(_optional_text(record, "posted_at"), "feed published"),
            source_updated_at=_feed_timestamp(
                _optional_text(record, "source_updated_at"), "feed updated"
            ),
            locations=_deduplicated_locations([location] if location is not None else []),
            employment_type=_employment_type(_optional_text(record, "employment_type")),
            source_status=_required_text(record, "source_status"),
        )

    def _require_permitted_job_url(self, value: str) -> None:
        try:
            _public_https_url(value, "feed job URL")
            host = _public_host(urlsplit(value).hostname or "", "feed job URL")
        except ValueError as exc:
            raise LiveSourceRecordError("feed job URL is unsafe") from exc
        if not any(host == allowed or host.endswith("." + allowed) for allowed in self.config.permitted_job_hosts):
            raise LiveSourceRecordError("feed job URL host is not configured")


def _feed_description(value: str | None) -> str | None:
    return _html_to_text(value) if value is not None else None


def create_live_adapter(
    config: LiveJobSourceConfig,
    *,
    timeout_seconds: float = 10.0,
    client: httpx.Client | None = None,
) -> LiveSourceAdapter:
    """Build one configured public adapter without network activity."""

    from backend.app.ingestion.structured import JsonLdAdapter, PersonioAdapter, RecruiteeAdapter

    adapters: dict[str, type[LiveSourceAdapter]] = {
        "greenhouse": GreenhouseAdapter,
        "lever": LeverAdapter,
        "ashby": AshbyAdapter,
        "smartrecruiters": SmartRecruitersAdapter,
        "rss": RssFeedAdapter,
        "recruitee": RecruiteeAdapter,
        "personio": PersonioAdapter,
        "jsonld": JsonLdAdapter,
    }
    return adapters[config.family](config, timeout_seconds=timeout_seconds, client=client)


__all__ = [
    "AshbyAdapter",
    "GreenhouseAdapter",
    "LeverAdapter",
    "LIVE_SOURCE_FAMILIES",
    "LiveJobSourceConfig",
    "LiveSourceAdapter",
    "LiveFetchResult",
    "LiveSourceConfigurationError",
    "LiveSourceFetchError",
    "LiveSourceRecordError",
    "RssFeedAdapter",
    "SmartRecruitersAdapter",
    "create_live_adapter",
    "load_live_source_configs",
]
