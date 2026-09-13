"""Private persistence queries used only by the internal job-ingestion service."""

from __future__ import annotations

import hashlib

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from backend.app.models.job import (
    JobSourceObservation,
    JobSourceRecord,
    NormalizedJob,
    RawJobSnapshot,
)
from backend.app.models.taxonomy import Company, Industry, Role, Skill, SkillAlias


class JobIngestionRepository:
    """Locks source identities and resolves only existing taxonomy rows."""

    def __init__(self, session):
        self.session = session

    def source_for_update(self, adapter_key: str, external_id: str) -> JobSourceRecord | None:
        return self.session.scalar(
            select(JobSourceRecord)
            .where(
                JobSourceRecord.source_adapter == adapter_key,
                JobSourceRecord.external_id == external_id,
            )
            .with_for_update()
        )

    def source_upsert_locked(
        self, adapter_key: str, external_id: str, source_url: str
    ) -> JobSourceRecord:
        """Return a locked source row, safely handling a concurrent first insert."""
        source = self.source_for_update(adapter_key, external_id)
        if source is not None:
            return source

        source = JobSourceRecord(
            source_adapter=adapter_key,
            external_id=external_id,
            source_url=source_url,
        )
        try:
            with self.session.begin_nested():
                self.session.add(source)
                self.session.flush()
            return source
        except IntegrityError:
            # Another transaction won the unique-key race.  Its committed row is
            # now locked before continuing, so subsequent snapshot/job writes are
            # serialized per external source identity.
            existing = self.source_for_update(adapter_key, external_id)
            if existing is None:
                raise
            return existing

    def snapshot_exists(self, source_id, payload_hash: str) -> bool:
        return (
            self.session.scalar(
                select(RawJobSnapshot.id).where(
                    RawJobSnapshot.job_source_record_id == source_id,
                    RawJobSnapshot.payload_hash_sha256 == payload_hash,
                )
            )
            is not None
        )

    def normalized_job_for_source(self, source_id) -> NormalizedJob | None:
        return self.session.scalar(
            select(NormalizedJob)
            .where(NormalizedJob.job_source_record_id == source_id)
            .with_for_update()
        )

    def observation_for_source_for_update(self, source_id) -> JobSourceObservation | None:
        return self.session.scalar(
            select(JobSourceObservation)
            .where(JobSourceObservation.job_source_record_id == source_id)
            .with_for_update()
        )

    def canonical_job_for_update(self, job_id) -> NormalizedJob | None:
        return self.session.scalar(
            select(NormalizedJob).where(NormalizedJob.id == job_id).with_for_update()
        )

    def lock_deduplication_fingerprints(self, fingerprints: tuple[str, ...]) -> None:
        """Serialize competing canonical decisions without a broad table lock."""

        for fingerprint in sorted(set(fingerprints)):
            advisory_key = int.from_bytes(
                hashlib.sha256(fingerprint.encode("ascii")).digest()[:8],
                byteorder="big",
                signed=True,
            )
            self.session.execute(select(func.pg_advisory_xact_lock(advisory_key)))

    def observations_matching_fingerprints_for_update(
        self,
        *,
        application_url_fingerprint: str,
        source_url_fingerprint: str,
        company_title_location_fingerprint: str | None,
    ) -> tuple[JobSourceObservation, ...]:
        predicates = [
            JobSourceObservation.application_url_fingerprint == application_url_fingerprint,
            JobSourceObservation.source_url_fingerprint == source_url_fingerprint,
        ]
        if company_title_location_fingerprint is not None:
            predicates.append(
                JobSourceObservation.company_title_location_fingerprint
                == company_title_location_fingerprint
            )
        return tuple(
            self.session.scalars(
                select(JobSourceObservation).where(or_(*predicates)).with_for_update()
            ).all()
        )

    def observations_for_canonical_for_update(self, canonical_job_id) -> tuple[JobSourceObservation, ...]:
        return tuple(
            self.session.scalars(
                select(JobSourceObservation)
                .where(JobSourceObservation.canonical_job_id == canonical_job_id)
                .order_by(JobSourceObservation.id)
                .with_for_update()
            ).all()
        )

    def observations_absent_from_successful_source_refresh_for_update(
        self,
        source_adapter: str,
        observed_external_ids: tuple[str, ...],
    ) -> tuple[JobSourceObservation, ...]:
        statement = (
            select(JobSourceObservation)
            .join(
                JobSourceRecord,
                JobSourceRecord.id == JobSourceObservation.job_source_record_id,
            )
            .where(JobSourceRecord.source_adapter == source_adapter)
            .with_for_update()
        )
        if observed_external_ids:
            statement = statement.where(
                JobSourceRecord.external_id.not_in(observed_external_ids)
            )
        return tuple(self.session.scalars(statement.order_by(JobSourceObservation.id)).all())

    def _unambiguous(self, statement):
        """Return the only matching catalog row; ambiguity is not normalization."""
        matches = self.session.scalars(statement.limit(2)).all()
        return matches[0] if len(matches) == 1 else None

    def company_by_name(self, name: str) -> Company | None:
        return self._unambiguous(
            select(Company).where(func.lower(Company.name) == name.casefold())
        )

    def active_role_by_name(self, name: str) -> Role | None:
        return self._unambiguous(
            select(Role).where(func.lower(Role.name) == name.casefold(), Role.is_active.is_(True))
        )

    def active_skill_or_alias(self, name: str) -> Skill | None:
        skill = self._unambiguous(
            select(Skill).where(func.lower(Skill.name) == name.casefold(), Skill.is_active.is_(True))
        )
        if skill is not None:
            return skill
        # An exact canonical name takes precedence over aliases. If it had
        # multiple catalog matches, reject it instead of silently taking an
        # alias that would make the normalized requirement nondeterministic.
        canonical_count = len(
            self.session.scalars(
                select(Skill.id)
                .where(func.lower(Skill.name) == name.casefold(), Skill.is_active.is_(True))
                .limit(2)
            ).all()
        )
        if canonical_count:
            return None
        return self._unambiguous(
            select(Skill)
            .join(SkillAlias, SkillAlias.skill_id == Skill.id)
            .where(
                SkillAlias.normalized_alias == name.casefold(),
                Skill.is_active.is_(True),
            )
        )

    def industry_by_name(self, name: str) -> Industry | None:
        return self._unambiguous(
            select(Industry).where(func.lower(Industry.name) == name.casefold())
        )
