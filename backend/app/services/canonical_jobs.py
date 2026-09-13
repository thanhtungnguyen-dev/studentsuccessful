"""Conservative canonical-job resolution over independently observed sources."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy import delete, select

from backend.app.core.config import settings
from backend.app.models.job import (
    JobEducationRequirement,
    JobEligibilityRequirement,
    JobIndustry,
    JobLifecycle,
    JobLocation,
    JobSkillRequirement,
    JobSourceAuthority,
    JobSourceObservation,
    NormalizedJob,
)
from backend.app.repositories.job_ingestion import JobIngestionRepository
from backend.app.services.job_alerts import JobAlertService

if TYPE_CHECKING:
    from backend.app.services.job_ingestion import PreparedJob


_AUTHORITY_RANK = {
    JobSourceAuthority.OFFICIAL_COMPANY: 0,
    JobSourceAuthority.OFFICIAL_ATS: 1,
    JobSourceAuthority.TRUSTED_STRUCTURED: 2,
    JobSourceAuthority.TRUSTED_AGGREGATOR: 3,
    JobSourceAuthority.UNKNOWN: 4,
}
_TRACKING_QUERY_KEYS = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid"})
_UNKNOWN = "UNSPECIFIED"


def normalize_source_authority(value: object) -> str:
    """Return an explicit generic authority class, never an adapter-family guess."""

    if isinstance(value, str) and value in _AUTHORITY_RANK:
        return value
    return JobSourceAuthority.UNKNOWN


def canonical_url_fingerprint(value: str) -> str:
    """Hash a conservatively canonicalized HTTP URL for deterministic matching."""

    parsed = urlsplit(value)
    hostname = (parsed.hostname or "").casefold()
    if ":" in hostname:
        hostname = f"[{hostname}]"
    port = parsed.port
    if port is not None and (parsed.scheme.casefold(), port) not in {("http", 80), ("https", 443)}:
        hostname = f"{hostname}:{port}"
    pairs = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_QUERY_KEYS
    ]
    canonical = urlunsplit(
        (
            parsed.scheme.casefold(),
            hostname,
            parsed.path.rstrip("/"),
            urlencode(pairs, doseq=True),
            "",
        )
    )
    return _fingerprint(canonical)


def company_title_location_fingerprint(
    company_id: object,
    title: str,
    locations: tuple[str, ...],
) -> str | None:
    """Return strong exact identity only when structured location is known."""

    normalized_locations = tuple(
        sorted({" ".join(value.split()).casefold() for value in locations if value.strip()})
    )
    if not normalized_locations:
        return None
    normalized_title = " ".join(title.split()).casefold()
    value = "\x1f".join((str(company_id), normalized_title, *normalized_locations))
    return _fingerprint(value)


def _fingerprint(value: str) -> str:
    """Return a portable 64-character deterministic key for indexed identity."""

    encoded = value.encode("utf-8")
    return hashlib.md5(encoded).hexdigest() + hashlib.md5(
        b"phase20:" + encoded
    ).hexdigest()


def _projection(item: PreparedJob) -> dict[str, object]:
    return {
        "locations": list(item.dto.locations),
        "industry_ids": [str(value) for value in item.industry_ids],
        "skills": [
            {
                "skill_id": str(skill_id),
                "importance": importance,
                "description": description,
            }
            for skill_id, importance, description in item.skill_requirements
        ],
        "education": [
            {
                "degree_level": value["degree_level"],
                "target_grad_start": (
                    value["target_grad_start"].isoformat()
                    if value["target_grad_start"] is not None
                    else None
                ),
                "target_grad_end": (
                    value["target_grad_end"].isoformat()
                    if value["target_grad_end"] is not None
                    else None
                ),
            }
            for value in item.education_requirements
        ],
        "eligibility": [dict(value) for value in item.eligibility_requirements],
    }


def _authority_rank(observation: JobSourceObservation) -> int:
    return _AUTHORITY_RANK.get(observation.source_authority, _AUTHORITY_RANK[JobSourceAuthority.UNKNOWN])


def _ranking_key(observation: JobSourceObservation) -> tuple[int, int, float, str]:
    """Prefer authority, then completeness, then a deterministic source revision."""

    completeness = sum(
        (
            bool(observation.description),
            observation.employment_type != _UNKNOWN,
            observation.work_mode != _UNKNOWN,
            observation.posted_at is not None,
        )
    )
    revision = observation.source_updated_at or observation.last_verified_at
    revision_seconds = revision.timestamp() if revision is not None else 0.0
    return (_authority_rank(observation), -completeness, -revision_seconds, str(observation.id))


def _first_known(
    observations: tuple[JobSourceObservation, ...],
    attribute: str,
    *,
    unknown: str | None = None,
):
    for observation in observations:
        value = getattr(observation, attribute)
        if value is not None and value != unknown:
            return value
    return None


def _projection_values(projection: dict[str, object] | None, key: str) -> list[object] | None:
    if not projection:
        return None
    value = projection.get(key)
    return value if isinstance(value, list) else None


@dataclass(frozen=True)
class CanonicalJobUpsert:
    """Write outcome used only for small per-source operational metrics."""

    job: NormalizedJob
    canonical_created: bool
    source_observation_created: bool


class CanonicalJobService:
    """Resolve user-visible jobs while retaining every source observation."""

    @staticmethod
    def upsert_source_observation(
        item: PreparedJob,
        source,
        repository: JobIngestionRepository,
        session,
        now: datetime,
    ) -> CanonicalJobUpsert:
        source_fingerprint = canonical_url_fingerprint(item.dto.source_url)
        application_fingerprint = canonical_url_fingerprint(item.dto.application_url)
        exact_fingerprint = company_title_location_fingerprint(
            item.company_id, item.dto.title, item.dto.locations
        )
        fingerprint_lock_set = (source_fingerprint, application_fingerprint) + (
            (exact_fingerprint,) if exact_fingerprint is not None else ()
        )
        repository.lock_deduplication_fingerprints(fingerprint_lock_set)

        observation = repository.observation_for_source_for_update(source.id)
        canonical_created = False
        source_observation_created = False
        if observation is None:
            source_observation_created = True
            candidates = repository.observations_matching_fingerprints_for_update(
                application_url_fingerprint=application_fingerprint,
                source_url_fingerprint=source_fingerprint,
                company_title_location_fingerprint=exact_fingerprint,
            )
            canonical_job = CanonicalJobService._matched_canonical(
                candidates,
                source_fingerprint=source_fingerprint,
                application_fingerprint=application_fingerprint,
                exact_fingerprint=exact_fingerprint,
                repository=repository,
            )
            if canonical_job is None:
                canonical_created = True
                canonical_job = NormalizedJob(
                    job_source_record_id=source.id,
                    company_id=item.company_id,
                    role_id=item.role_id,
                    title=item.dto.title,
                    description=item.dto.description,
                    employment_type=item.dto.employment_type,
                    career_level=item.dto.career_level,
                    work_mode=item.dto.work_mode,
                    application_url=item.dto.application_url,
                    current_payload_hash_sha256=item.payload_hash,
                    discovered_at=now,
                    first_seen_at=now,
                    last_seen_at=now,
                    last_verified_at=now,
                    canonical_updated_at=now,
                )
                session.add(canonical_job)
                session.flush()
            observation = JobSourceObservation(
                canonical_job_id=canonical_job.id,
                job_source_record_id=source.id,
                first_seen_at=now,
            )
            session.add(observation)
        else:
            canonical_job = repository.canonical_job_for_update(observation.canonical_job_id)
            if canonical_job is None:
                raise RuntimeError("source observation has no canonical job")

        CanonicalJobService._apply_source_facts(
            observation,
            item,
            source_fingerprint=source_fingerprint,
            application_fingerprint=application_fingerprint,
            exact_fingerprint=exact_fingerprint,
            now=now,
        )
        session.flush()
        CanonicalJobService.resolve_canonical(canonical_job, repository, session, now)
        if canonical_created:
            # New-job alert events share this ingestion transaction. A duplicate
            # source observation never reaches this path.
            JobAlertService.evaluate_new_canonical_job(canonical_job.id, session, now)
        return CanonicalJobUpsert(
            job=canonical_job,
            canonical_created=canonical_created,
            source_observation_created=source_observation_created,
        )

    @staticmethod
    def record_successful_source_refresh(
        source_adapter: str,
        observed_external_ids: tuple[str, ...],
        repository: JobIngestionRepository,
        session,
        completed_at: datetime,
    ) -> None:
        """Apply absence evidence only after a complete, successful source listing."""

        affected_canonical_ids: set[object] = set()
        for observation in repository.observations_absent_from_successful_source_refresh_for_update(
            source_adapter,
            observed_external_ids,
        ):
            if observation.explicitly_closed:
                continue
            observation.consecutive_absent_successes += 1
            observation.last_absent_at = completed_at
            observation.updated_at = completed_at
            affected_canonical_ids.add(observation.canonical_job_id)
        for canonical_job_id in sorted(affected_canonical_ids, key=str):
            canonical_job = repository.canonical_job_for_update(canonical_job_id)
            if canonical_job is not None:
                CanonicalJobService.resolve_canonical(
                    canonical_job, repository, session, completed_at
                )

    @staticmethod
    def resolve_canonical(
        canonical_job: NormalizedJob,
        repository: JobIngestionRepository,
        session,
        now: datetime,
    ) -> None:
        observations = repository.observations_for_canonical_for_update(canonical_job.id)
        if not observations:
            return
        canonical_job.last_seen_at = max(
            observation.last_seen_at for observation in observations if observation.last_seen_at
        )
        canonical_job.last_verified_at = max(
            observation.last_verified_at
            for observation in observations
            if observation.last_verified_at
        )

        explicit_authoritative_closure = any(
            observation.explicitly_closed
            and _authority_rank(observation) <= _AUTHORITY_RANK[JobSourceAuthority.OFFICIAL_ATS]
            for observation in observations
        )
        supporting = tuple(
            sorted(
                (
                    observation
                    for observation in observations
                    if not observation.explicitly_closed
                    and observation.consecutive_absent_successes == 0
                ),
                key=_ranking_key,
            )
        )
        if explicit_authoritative_closure:
            CanonicalJobService._set_lifecycle(canonical_job, JobLifecycle.CLOSED, now)
            return
        if supporting:
            CanonicalJobService._apply_resolved_presentation(
                canonical_job, supporting, session, now
            )
            CanonicalJobService._set_lifecycle(canonical_job, JobLifecycle.ACTIVE, now)
            return

        close_after = max(2, settings.JOB_CLOSE_AFTER_SUCCESSFUL_ABSENCES)
        all_absent_after_grace = all(
            observation.consecutive_absent_successes >= close_after
            for observation in observations
        )
        CanonicalJobService._set_lifecycle(
            canonical_job,
            JobLifecycle.CLOSED if all_absent_after_grace else JobLifecycle.STALE,
            now,
        )

    @staticmethod
    def _matched_canonical(
        candidates: tuple[JobSourceObservation, ...],
        *,
        source_fingerprint: str,
        application_fingerprint: str,
        exact_fingerprint: str | None,
        repository: JobIngestionRepository,
    ) -> NormalizedJob | None:
        scores: dict[object, int] = {}
        for candidate in candidates:
            score = 0
            if candidate.application_url_fingerprint == application_fingerprint:
                score = max(score, 300)
            if candidate.source_url_fingerprint == source_fingerprint:
                score = max(score, 200)
            if (
                exact_fingerprint is not None
                and candidate.company_title_location_fingerprint == exact_fingerprint
            ):
                score = max(score, 100)
            if score:
                scores[candidate.canonical_job_id] = max(
                    score, scores.get(candidate.canonical_job_id, 0)
                )
        for canonical_job_id, _ in sorted(
            scores.items(), key=lambda value: (-value[1], str(value[0]))
        ):
            canonical_job = repository.canonical_job_for_update(canonical_job_id)
            if canonical_job is not None:
                return canonical_job
        return None

    @staticmethod
    def _apply_source_facts(
        observation: JobSourceObservation,
        item: PreparedJob,
        *,
        source_fingerprint: str,
        application_fingerprint: str,
        exact_fingerprint: str | None,
        now: datetime,
    ) -> None:
        observation.source_authority = item.source_authority
        observation.source_url = item.dto.source_url
        observation.application_url = item.dto.application_url
        observation.source_url_fingerprint = source_fingerprint
        observation.application_url_fingerprint = application_fingerprint
        observation.company_title_location_fingerprint = exact_fingerprint
        observation.company_id = item.company_id
        observation.role_id = item.role_id
        observation.title = item.dto.title
        observation.description = item.dto.description
        observation.employment_type = item.dto.employment_type
        observation.career_level = item.dto.career_level
        observation.work_mode = item.dto.work_mode
        observation.posted_at = item.dto.posted_at
        observation.source_updated_at = item.dto.source_updated_at
        observation.fact_projection = _projection(item)
        observation.current_payload_hash_sha256 = item.payload_hash
        observation.last_seen_at = now
        observation.last_verified_at = now
        observation.consecutive_absent_successes = 0
        observation.last_absent_at = None
        observation.explicitly_closed = item.dto.source_status == "CLOSED"
        observation.closed_at = now if observation.explicitly_closed else None
        observation.updated_at = now

    @staticmethod
    def _apply_resolved_presentation(
        canonical_job: NormalizedJob,
        observations: tuple[JobSourceObservation, ...],
        session,
        now: datetime,
    ) -> None:
        primary = observations[0]
        application_source = min(
            observations,
            key=lambda observation: (
                CanonicalJobService._apply_quality(observation),
                _authority_rank(observation),
                _ranking_key(observation),
            ),
        )
        projection_source = next(
            (observation for observation in observations if observation.fact_projection is not None),
            None,
        )
        projection = (
            projection_source.fact_projection if projection_source is not None else None
        )
        desired_locations = _projection_values(projection, "locations")
        desired_skills = _projection_values(projection, "skills")
        desired_education = _projection_values(projection, "education")
        desired_eligibility = _projection_values(projection, "eligibility")
        desired_industries = _projection_values(projection, "industry_ids")

        description = _first_known(observations, "description")
        employment_type = _first_known(
            observations, "employment_type", unknown=_UNKNOWN
        ) or _UNKNOWN
        career_level = _first_known(observations, "career_level", unknown=_UNKNOWN) or _UNKNOWN
        work_mode = _first_known(observations, "work_mode", unknown=_UNKNOWN) or _UNKNOWN
        posted_at = _first_known(observations, "posted_at")
        last_seen_at = max(
            observation.last_seen_at for observation in observations if observation.last_seen_at
        )
        last_verified_at = max(
            observation.last_verified_at
            for observation in observations
            if observation.last_verified_at
        )

        presentation_changed = CanonicalJobService._presentation_changed(
            canonical_job,
            primary=primary,
            application_source=application_source,
            description=description,
            employment_type=employment_type,
            career_level=career_level,
            work_mode=work_mode,
            posted_at=posted_at,
            projection=projection,
            session=session,
        )
        canonical_job.company_id = primary.company_id
        canonical_job.role_id = primary.role_id
        canonical_job.title = primary.title
        canonical_job.description = description
        canonical_job.employment_type = employment_type
        canonical_job.career_level = career_level
        canonical_job.work_mode = work_mode
        canonical_job.application_url = application_source.application_url
        canonical_job.posted_at = posted_at
        canonical_job.current_payload_hash_sha256 = primary.current_payload_hash_sha256
        canonical_job.canonical_source_observation_id = primary.id
        canonical_job.application_source_observation_id = application_source.id
        canonical_job.last_seen_at = last_seen_at
        canonical_job.last_verified_at = last_verified_at
        if presentation_changed:
            if projection is not None:
                CanonicalJobService._replace_requirements(
                    canonical_job.id,
                    session,
                    locations=desired_locations or [],
                    industry_ids=desired_industries or [],
                    skills=desired_skills or [],
                    education=desired_education or [],
                    eligibility=desired_eligibility or [],
                )
            canonical_job.canonical_updated_at = now

    @staticmethod
    def _apply_quality(observation: JobSourceObservation) -> int:
        if _authority_rank(observation) <= _AUTHORITY_RANK[JobSourceAuthority.OFFICIAL_ATS]:
            return 0 if (
                observation.application_url_fingerprint
                != observation.source_url_fingerprint
            ) else 1
        if observation.source_authority == JobSourceAuthority.TRUSTED_STRUCTURED:
            return 3
        if observation.source_authority == JobSourceAuthority.TRUSTED_AGGREGATOR:
            return 4
        return 5

    @staticmethod
    def _presentation_changed(
        canonical_job: NormalizedJob,
        *,
        primary: JobSourceObservation,
        application_source: JobSourceObservation,
        description: str | None,
        employment_type: str,
        career_level: str,
        work_mode: str,
        posted_at: datetime | None,
        projection: dict[str, object] | None,
        session,
    ) -> bool:
        fields_changed = (
            canonical_job.company_id != primary.company_id
            or canonical_job.role_id != primary.role_id
            or canonical_job.title != primary.title
            or canonical_job.description != description
            or canonical_job.employment_type != employment_type
            or canonical_job.career_level != career_level
            or canonical_job.work_mode != work_mode
            or canonical_job.application_url != application_source.application_url
            or canonical_job.posted_at != posted_at
            or canonical_job.canonical_source_observation_id != primary.id
            or canonical_job.application_source_observation_id != application_source.id
        )
        if fields_changed or projection is None:
            return fields_changed
        return CanonicalJobService._current_projection(
            canonical_job.id, session
        ) != CanonicalJobService._normalized_projection(projection)

    @staticmethod
    def _current_projection(job_id, session) -> dict[str, object]:
        return {
            "locations": list(
                session.scalars(
                    select(JobLocation.location_raw)
                    .where(JobLocation.job_id == job_id)
                    .order_by(JobLocation.location_raw, JobLocation.id)
                )
            ),
            "industry_ids": [
                str(value)
                for value in session.scalars(
                    select(JobIndustry.industry_id)
                    .where(JobIndustry.job_id == job_id)
                    .order_by(JobIndustry.industry_id)
                )
            ],
            "skills": [
                {
                    "skill_id": str(row.skill_id),
                    "importance": row.importance,
                    "description": row.description,
                }
                for row in session.execute(
                    select(
                        JobSkillRequirement.skill_id,
                        JobSkillRequirement.importance,
                        JobSkillRequirement.description,
                    )
                    .where(JobSkillRequirement.job_id == job_id)
                    .order_by(JobSkillRequirement.skill_id)
                )
            ],
            "education": [
                {
                    "degree_level": row.degree_level,
                    "target_grad_start": (
                        row.target_grad_start.isoformat()
                        if row.target_grad_start is not None
                        else None
                    ),
                    "target_grad_end": (
                        row.target_grad_end.isoformat()
                        if row.target_grad_end is not None
                        else None
                    ),
                }
                for row in session.execute(
                    select(
                        JobEducationRequirement.degree_level,
                        JobEducationRequirement.target_grad_start,
                        JobEducationRequirement.target_grad_end,
                    )
                    .where(JobEducationRequirement.job_id == job_id)
                    .order_by(
                        JobEducationRequirement.degree_level,
                        JobEducationRequirement.target_grad_start,
                        JobEducationRequirement.target_grad_end,
                    )
                )
            ],
            "eligibility": [
                {
                    "requirement_type": row.requirement_type,
                    "value": row.value,
                    "description": row.description,
                }
                for row in session.execute(
                    select(
                        JobEligibilityRequirement.requirement_type,
                        JobEligibilityRequirement.value,
                        JobEligibilityRequirement.description,
                    )
                    .where(JobEligibilityRequirement.job_id == job_id)
                    .order_by(
                        JobEligibilityRequirement.requirement_type,
                        JobEligibilityRequirement.value,
                    )
                )
            ],
        }

    @staticmethod
    def _normalized_projection(projection: dict[str, object]) -> dict[str, object]:
        def ordered(values: list[object] | None, key):
            return sorted(values or [], key=key)

        return {
            "locations": sorted(_projection_values(projection, "locations") or []),
            "industry_ids": sorted(_projection_values(projection, "industry_ids") or []),
            "skills": ordered(
                _projection_values(projection, "skills"),
                lambda value: str(value["skill_id"]),
            ),
            "education": ordered(
                _projection_values(projection, "education"),
                lambda value: (
                    value["degree_level"],
                    value["target_grad_start"] or "",
                    value["target_grad_end"] or "",
                ),
            ),
            "eligibility": ordered(
                _projection_values(projection, "eligibility"),
                lambda value: (
                    value["requirement_type"],
                    value["value"],
                ),
            ),
        }

    @staticmethod
    def _replace_requirements(
        job_id,
        session,
        *,
        locations: list[object],
        industry_ids: list[object],
        skills: list[object],
        education: list[object],
        eligibility: list[object],
    ) -> None:
        session.execute(delete(JobIndustry).where(JobIndustry.job_id == job_id))
        session.execute(delete(JobLocation).where(JobLocation.job_id == job_id))
        session.execute(delete(JobSkillRequirement).where(JobSkillRequirement.job_id == job_id))
        session.execute(delete(JobEducationRequirement).where(JobEducationRequirement.job_id == job_id))
        session.execute(delete(JobEligibilityRequirement).where(JobEligibilityRequirement.job_id == job_id))
        session.add_all(
            JobIndustry(job_id=job_id, industry_id=UUID(str(industry_id)))
            for industry_id in industry_ids
        )
        session.add_all(
            JobLocation(job_id=job_id, location_raw=str(location))
            for location in locations
        )
        session.add_all(
            JobSkillRequirement(
                job_id=job_id,
                skill_id=UUID(str(skill["skill_id"])),
                importance=skill["importance"],
                description=skill["description"],
            )
            for skill in skills
        )
        session.add_all(
            JobEducationRequirement(
                job_id=job_id,
                degree_level=education_item["degree_level"],
                target_grad_start=CanonicalJobService._date(
                    education_item["target_grad_start"]
                ),
                target_grad_end=CanonicalJobService._date(education_item["target_grad_end"]),
            )
            for education_item in education
        )
        session.add_all(
            JobEligibilityRequirement(
                job_id=job_id,
                requirement_type=eligibility_item["requirement_type"],
                value=eligibility_item["value"],
                description=eligibility_item["description"],
            )
            for eligibility_item in eligibility
        )

    @staticmethod
    def _set_lifecycle(
        canonical_job: NormalizedJob,
        lifecycle: str,
        now: datetime,
    ) -> None:
        if canonical_job.lifecycle != lifecycle:
            canonical_job.canonical_updated_at = now
        canonical_job.lifecycle = lifecycle
        canonical_job.is_active = lifecycle != JobLifecycle.CLOSED
        canonical_job.closed_at = now if lifecycle == JobLifecycle.CLOSED else None

    @staticmethod
    def _date(value: object) -> date | None:
        return date.fromisoformat(value) if isinstance(value, str) else None


__all__ = [
    "CanonicalJobService",
    "CanonicalJobUpsert",
    "canonical_url_fingerprint",
    "company_title_location_fingerprint",
    "normalize_source_authority",
]
