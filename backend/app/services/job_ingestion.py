"""Transactional internal ingestion of externally fetched shared job facts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

from backend.app.ingestion.adapters import SourceAdapterRegistry, UnsupportedSourceAdapterError
from backend.app.ingestion.dto import ExternalJobDTO
from backend.app.models.job import NormalizedJob, RawJobSnapshot
from backend.app.repositories.job_ingestion import JobIngestionRepository
from backend.app.services.canonical_jobs import (
    CanonicalJobService,
    normalize_source_authority,
)


class JobIngestionValidationError(ValueError):
    """A rejected external record; no partial ingestion is allowed."""


_CONTROL_OR_WHITESPACE = re.compile(r"[\x00-\x20\x7f]")
_COMPANY_SUFFIXES = re.compile(
    r"(?:[,.\s]+(?:incorporated|inc|llc|l\.l\.c\.|ltd|limited|corp(?:oration)?|co(?:mpany)?))+$",
    re.IGNORECASE,
)
_MAX_TEXT = 20_000


@dataclass(frozen=True)
class PreparedJob:
    dto: ExternalJobDTO
    payload: dict
    payload_hash: str
    company_id: object
    role_id: object
    skill_requirements: tuple[tuple[object, str, str | None], ...]
    education_requirements: tuple[dict, ...]
    eligibility_requirements: tuple[dict, ...]
    industry_ids: tuple[object, ...]
    source_authority: str


@dataclass(frozen=True)
class IngestedJobOutcome:
    """Small internal write result for collector value metrics."""

    job: NormalizedJob
    canonical_created: bool
    source_observation_created: bool


def _plain_text(value: str | None, field: str, *, max_length: int = _MAX_TEXT, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise JobIngestionValidationError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise JobIngestionValidationError(f"{field} must be text")
    normalized = " ".join(value.split())
    if required and not normalized:
        raise JobIngestionValidationError(f"{field} must not be blank")
    if len(normalized) > max_length:
        raise JobIngestionValidationError(f"{field} exceeds its maximum length")
    return normalized


def _safe_url(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or _CONTROL_OR_WHITESPACE.search(value) or "\\" in value:
        raise JobIngestionValidationError(f"{field} must be a safe absolute http(s) URL")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise JobIngestionValidationError(f"{field} must be a safe absolute http(s) URL")
    try:
        parsed.port
    except ValueError as exc:
        raise JobIngestionValidationError(f"{field} must have a valid URL port") from exc
    if len(value) > 1000:
        raise JobIngestionValidationError(f"{field} exceeds its maximum length")
    return value


def normalize_company_identity(value: str) -> str:
    normalized = _plain_text(value, "company", max_length=150, required=True)
    assert normalized is not None
    normalized = _COMPANY_SUFFIXES.sub("", normalized).strip(" ,.")
    if not normalized:
        raise JobIngestionValidationError("company must contain a canonical name")
    return normalized


def _location(value: str) -> str:
    normalized = _plain_text(value, "location", max_length=255, required=True)
    assert normalized is not None
    aliases = {
        "remote": "Remote",
        "toronto, canada": "Toronto, Canada",
        "toronto canada": "Toronto, Canada",
    }
    return aliases.get(normalized.casefold(), normalized)


def _canonical_json(payload: dict) -> tuple[dict, str]:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=lambda value: value.isoformat(),
    )
    # JSON decode makes the stored JSONB structurally canonical without accepting
    # caller-controlled raw payloads or a caller-provided digest.
    return json.loads(encoded), hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class JobIngestionService:
    """Ingest a strict adapter result with one explicit UoW commit."""

    @staticmethod
    def ingest_from_adapter(adapter_key: str, registry: SourceAdapterRegistry, uow):
        adapter = registry.resolve(adapter_key)
        fetched = tuple(adapter.fetch())  # fetches before any database access/transaction
        for record in fetched:
            if not isinstance(record, ExternalJobDTO):
                raise JobIngestionValidationError("adapter results must be ExternalJobDTO records")
            if record.adapter_key != adapter_key:
                raise JobIngestionValidationError("adapter result has a mismatched adapter key")
        return JobIngestionService.ingest_many(fetched, registry, uow)

    @staticmethod
    def ingest(record: ExternalJobDTO, registry: SourceAdapterRegistry, uow) -> NormalizedJob:
        return JobIngestionService.ingest_with_outcome(record, registry, uow).job

    @staticmethod
    def ingest_with_outcome(
        record: ExternalJobDTO,
        registry: SourceAdapterRegistry,
        uow,
    ) -> IngestedJobOutcome:
        return JobIngestionService._ingest_many_with_outcomes((record,), registry, uow)[0]

    @staticmethod
    def ingest_many(
        records: Iterable[ExternalJobDTO], registry: SourceAdapterRegistry, uow
    ) -> list[NormalizedJob]:
        return [
            outcome.job
            for outcome in JobIngestionService._ingest_many_with_outcomes(records, registry, uow)
        ]

    @staticmethod
    def _ingest_many_with_outcomes(
        records: Iterable[ExternalJobDTO],
        registry: SourceAdapterRegistry,
        uow,
    ) -> list[IngestedJobOutcome]:
        records = tuple(records)
        try:
            prepared = [JobIngestionService._prepare(record, registry, uow.session) for record in records]
            repository = JobIngestionRepository(uow.session)
            outcomes = [
                JobIngestionService._write(item, repository, uow.session) for item in prepared
            ]
            uow.commit()
            return outcomes
        except Exception:
            uow.rollback()
            raise

    @staticmethod
    def _prepare(record: ExternalJobDTO, registry: SourceAdapterRegistry, session) -> PreparedJob:
        if not isinstance(record, ExternalJobDTO):
            raise JobIngestionValidationError("record must be an ExternalJobDTO")
        adapter_key = _plain_text(record.adapter_key, "adapter_key", max_length=50, required=True)
        assert adapter_key is not None
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,49}", adapter_key):
            raise JobIngestionValidationError("adapter_key must be a safe identifier")
        try:
            registry.resolve(adapter_key)
        except UnsupportedSourceAdapterError as exc:
            raise JobIngestionValidationError(str(exc)) from exc
        source_authority = normalize_source_authority(registry.source_authority(adapter_key))

        external_id = _plain_text(record.external_id, "external_id", max_length=255, required=True)
        assert adapter_key is not None and external_id is not None
        source_url = _safe_url(record.source_url, "source_url")
        application_url = _safe_url(record.application_url, "application_url")
        company_name = normalize_company_identity(record.company)
        title = _plain_text(record.title, "title", max_length=200, required=True)
        role_name = _plain_text(record.role, "role", max_length=100, required=True)
        employment_type = _plain_text(record.employment_type, "employment_type", max_length=50, required=True)
        career_level = _plain_text(record.career_level, "career_level", max_length=50, required=True)
        work_mode = _plain_text(record.work_mode, "work_mode", max_length=30, required=True)
        description = _plain_text(record.description, "description", max_length=_MAX_TEXT)
        assert title is not None and role_name is not None and employment_type is not None
        assert career_level is not None and work_mode is not None

        repository = JobIngestionRepository(session)
        company = repository.company_by_name(company_name)
        if company is None:
            raise JobIngestionValidationError(f"Unknown company: {company_name}")
        role = repository.active_role_by_name(role_name)
        if role is None:
            raise JobIngestionValidationError(f"Unknown active role: {role_name}")

        locations = tuple(sorted({_location(value) for value in record.locations}, key=str.casefold))
        skill_rows: list[tuple[object, str, str | None, str]] = []
        seen_skills: set[object] = set()
        for requirement in record.skills:
            skill_name = _plain_text(requirement.skill, "skill", max_length=100, required=True)
            importance = _plain_text(requirement.importance, "skill importance", max_length=30, required=True)
            description_value = _plain_text(requirement.description, "skill description")
            assert skill_name is not None and importance is not None
            skill = repository.active_skill_or_alias(skill_name)
            if skill is None:
                raise JobIngestionValidationError(f"Unknown active skill: {skill_name}")
            if skill.id in seen_skills:
                raise JobIngestionValidationError("Duplicate skill requirement")
            seen_skills.add(skill.id)
            skill_rows.append((skill.id, importance, description_value, skill.name))
        skill_rows.sort(key=lambda row: (row[3].casefold(), str(row[0])))

        education = []
        seen_education = set()
        for requirement in record.education_requirements:
            degree = _plain_text(requirement.degree_level, "degree_level", max_length=50, required=True)
            assert degree is not None
            if (
                requirement.target_grad_start is not None
                and requirement.target_grad_end is not None
                and requirement.target_grad_start > requirement.target_grad_end
            ):
                raise JobIngestionValidationError(
                    "education target graduation start must not follow its end"
                )
            identity = (degree.casefold(), requirement.target_grad_start, requirement.target_grad_end)
            if identity in seen_education:
                raise JobIngestionValidationError("Duplicate education requirement")
            seen_education.add(identity)
            education.append({"degree_level": degree, "target_grad_start": requirement.target_grad_start, "target_grad_end": requirement.target_grad_end})
        education.sort(key=lambda value: (value["degree_level"].casefold(), str(value["target_grad_start"]), str(value["target_grad_end"])))

        eligibility = []
        seen_eligibility = set()
        for requirement in record.eligibility_requirements:
            requirement_type = _plain_text(requirement.requirement_type, "eligibility type", max_length=50, required=True)
            value = _plain_text(requirement.value, "eligibility value", max_length=100, required=True)
            description_value = _plain_text(requirement.description, "eligibility description")
            assert requirement_type is not None and value is not None
            identity = (requirement_type.casefold(), value.casefold())
            if identity in seen_eligibility:
                raise JobIngestionValidationError("Duplicate eligibility requirement")
            seen_eligibility.add(identity)
            eligibility.append({"requirement_type": requirement_type, "value": value, "description": description_value})
        eligibility.sort(key=lambda value: (value["requirement_type"].casefold(), value["value"].casefold()))

        industry_ids = []
        industry_names = []
        seen_industries = set()
        for value in record.industries:
            name = _plain_text(value, "industry", max_length=100, required=True)
            assert name is not None
            industry = repository.industry_by_name(name)
            if industry is None:
                raise JobIngestionValidationError(f"Unknown industry: {name}")
            if industry.id in seen_industries:
                raise JobIngestionValidationError("Duplicate industry")
            seen_industries.add(industry.id)
            industry_ids.append(industry.id)
            industry_names.append(industry.name)
        industry_pairs = sorted(zip(industry_names, industry_ids), key=lambda row: row[0].casefold())

        if record.posted_at is not None and (
            record.posted_at.tzinfo is None or record.posted_at.utcoffset() is None
        ):
            raise JobIngestionValidationError("posted_at must include a UTC offset")
        posted_at = record.posted_at.astimezone(timezone.utc) if record.posted_at else None
        if record.source_updated_at is not None and (
            record.source_updated_at.tzinfo is None or record.source_updated_at.utcoffset() is None
        ):
            raise JobIngestionValidationError("source_updated_at must include a UTC offset")
        source_updated_at = (
            record.source_updated_at.astimezone(timezone.utc) if record.source_updated_at else None
        )
        payload, payload_hash = _canonical_json(
            {
                "adapter_key": adapter_key,
                "application_url": application_url,
                "career_level": career_level,
                "company": company.name,
                "description": description,
                "education_requirements": education,
                "eligibility_requirements": eligibility,
                "employment_type": employment_type,
                "external_id": external_id,
                "industries": [name for name, _ in industry_pairs],
                "locations": list(locations),
                "posted_at": posted_at.isoformat().replace("+00:00", "Z") if posted_at else None,
                "role": role.name,
                "skills": [
                    {"skill": name, "importance": importance, "description": detail}
                    for _, importance, detail, name in skill_rows
                ],
                "source_url": source_url,
                "source_updated_at": (
                    source_updated_at.isoformat().replace("+00:00", "Z")
                    if source_updated_at
                    else None
                ),
                "source_status": record.source_status,
                "title": title,
                "work_mode": work_mode,
            }
        )
        normalized = ExternalJobDTO(
            adapter_key=adapter_key, external_id=external_id, source_url=source_url,
            application_url=application_url, company=company.name, title=title, role=role.name,
            employment_type=employment_type, career_level=career_level, work_mode=work_mode,
            description=description, posted_at=posted_at, source_updated_at=source_updated_at,
            source_status=record.source_status,
            locations=locations,
        )
        return PreparedJob(
            dto=normalized, payload=payload, payload_hash=payload_hash, company_id=company.id,
            role_id=role.id, skill_requirements=tuple((row[0], row[1], row[2]) for row in skill_rows),
            education_requirements=tuple(education), eligibility_requirements=tuple(eligibility),
            industry_ids=tuple(industry_id for _, industry_id in industry_pairs),
            source_authority=source_authority,
        )

    @staticmethod
    def _write(
        item: PreparedJob,
        repository: JobIngestionRepository,
        session,
    ) -> IngestedJobOutcome:
        source = repository.source_upsert_locked(item.dto.adapter_key, item.dto.external_id, item.dto.source_url)
        now = datetime.now(timezone.utc)
        # A source can return a previously seen payload after a later revision.
        # Snapshot presence deduplicates immutable provenance; it cannot be used
        # as a proxy for the currently applied normalized facts.
        snapshot_exists = repository.snapshot_exists(source.id, item.payload_hash)
        if not snapshot_exists:
            session.add(
                RawJobSnapshot(
                    job_source_record_id=source.id,
                    raw_payload=item.payload,
                    payload_hash_sha256=item.payload_hash,
                )
            )
        canonical = CanonicalJobService.upsert_source_observation(
            item, source, repository, session, now
        )
        return IngestedJobOutcome(
            job=canonical.job,
            canonical_created=canonical.canonical_created,
            source_observation_created=canonical.source_observation_created,
        )


__all__ = [
    "IngestedJobOutcome",
    "JobIngestionService",
    "JobIngestionValidationError",
    "PreparedJob",
]
