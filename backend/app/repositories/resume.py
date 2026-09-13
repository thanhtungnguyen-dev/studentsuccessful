"""Owner-scoped resume queries and persistence only; transaction ownership stays in services."""

from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from backend.app.models.application import Application
from backend.app.models.resume import (
    Resume,
    ResumeEvidenceItem,
    ResumeEvidenceSkill,
    ResumeVersion,
)
from backend.app.models.taxonomy import Skill, SkillAlias


class ResumeRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_for_owner(self, owner: UUID) -> list[Resume]:
        return list(
            self.session.scalars(
                select(Resume).where(Resume.user_id == owner).order_by(Resume.created_at, Resume.id)
            )
        )

    def owned_resume(self, owner: UUID, resume_id: UUID, *, lock: bool = False) -> Resume | None:
        query = select(Resume).where(Resume.user_id == owner, Resume.id == resume_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(query)

    def versions_for_resume(self, resume_id: UUID) -> list[ResumeVersion]:
        return list(
            self.session.scalars(
                select(ResumeVersion)
                .where(ResumeVersion.resume_id == resume_id)
                .order_by(ResumeVersion.version_number, ResumeVersion.id)
            )
        )

    def owned_version(
        self, owner: UUID, version_id: UUID, *, lock: bool = False
    ) -> ResumeVersion | None:
        """Return one exact version only when its resume belongs to ``owner``."""
        query = (
            select(ResumeVersion)
            .join(Resume, Resume.id == ResumeVersion.resume_id)
            .where(Resume.user_id == owner, ResumeVersion.id == version_id)
        )
        if lock:
            # Parse requests serialize only this immutable version.  Do not lock the
            # parent Resume joined for the ownership check, so separate versions can
            # parse independently.
            query = (
                query.with_for_update(of=ResumeVersion)
                .execution_options(populate_existing=True)
            )
        return self.session.scalar(query)

    def evidence_for_owned_version(self, owner: UUID, version_id: UUID) -> list[ResumeEvidenceItem]:
        """Return evidence in source order without exposing another owner's version."""
        return list(
            self.session.scalars(
                select(ResumeEvidenceItem)
                .join(ResumeVersion, ResumeVersion.id == ResumeEvidenceItem.resume_version_id)
                .join(Resume, Resume.id == ResumeVersion.resume_id)
                .where(Resume.user_id == owner, ResumeVersion.id == version_id)
                .order_by(ResumeEvidenceItem.ordinal, ResumeEvidenceItem.id)
            )
        )

    def replace_evidence_for_version(
        self, version_id: UUID, items: list[ResumeEvidenceItem]
    ) -> None:
        """Stage one exact version's replacement set; the service owns commit/rollback.

        Callers must lock and owner-check the version first.  The delete and inserts
        share the caller's transaction, so a parser error cannot commit a mixed set.
        """
        if any(item.resume_version_id != version_id for item in items):
            raise ValueError("Evidence item belongs to a different resume version")
        self.session.execute(
            delete(ResumeEvidenceItem).where(ResumeEvidenceItem.resume_version_id == version_id)
        )
        # Explicitly flush the delete before staging reused ordinals.  This remains
        # inside the caller's transaction; a later failure rolls the old rows back.
        self.session.flush()
        self.session.add_all(items)

    def skill_terms_for_matching(self) -> list[tuple[UUID, str, str]]:
        """Return only existing active catalog terms; this never creates taxonomy rows."""
        canonical = self.session.execute(
            select(Skill.id, Skill.name, Skill.name)
            .where(Skill.is_active.is_(True))
            .order_by(func.lower(Skill.name), Skill.id)
        ).all()
        aliases = self.session.execute(
            select(Skill.id, Skill.name, SkillAlias.normalized_alias)
            .join(SkillAlias, SkillAlias.skill_id == Skill.id)
            .where(Skill.is_active.is_(True))
            .order_by(func.lower(Skill.name), Skill.id, SkillAlias.id)
        ).all()
        return [
            (row[0], row[1], row[2])
            for row in [*canonical, *aliases]
            if isinstance(row[2], str)
        ]

    def skills_for_evidence_items(
        self, evidence_item_ids: list[UUID]
    ) -> list[tuple[UUID, UUID, str, object]]:
        """Read persisted parser links and canonical names in deterministic order."""
        if not evidence_item_ids:
            return []
        rows = self.session.execute(
            select(
                ResumeEvidenceSkill.evidence_item_id,
                Skill.id,
                Skill.name,
                ResumeEvidenceSkill.parser_confidence,
            )
            .join(Skill, Skill.id == ResumeEvidenceSkill.skill_id)
            .where(ResumeEvidenceSkill.evidence_item_id.in_(evidence_item_ids))
            .order_by(
                ResumeEvidenceSkill.evidence_item_id,
                func.lower(Skill.name),
                Skill.id,
            )
        ).all()
        return [(row[0], row[1], row[2], row[3]) for row in rows]

    def version_for_locked_resume(
        self, resume_id: UUID, version_id: UUID, *, lock: bool = False
    ) -> ResumeVersion | None:
        query = select(ResumeVersion).where(
            ResumeVersion.resume_id == resume_id, ResumeVersion.id == version_id
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(query)

    def next_version_number(self, resume_id: UUID) -> int:
        # Call only after locking the owning Resume aggregate.
        current = self.session.scalar(
            select(func.coalesce(func.max(ResumeVersion.version_number), 0)).where(
                ResumeVersion.resume_id == resume_id
            )
        )
        return int(current) + 1

    def has_versions(self, resume_id: UUID) -> bool:
        return (
            self.session.scalar(
                select(ResumeVersion.id).where(ResumeVersion.resume_id == resume_id).limit(1)
            )
            is not None
        )

    def version_is_recorded_on_application(self, version_id: UUID) -> bool:
        """A historical application reference must remain an immutable version link."""
        return (
            self.session.scalar(
                select(Application.id)
                .where(Application.resume_version_id == version_id)
                .limit(1)
            )
            is not None
        )

    def demote_other_primary_versions(self, resume_id: UUID, selected_version_id: UUID) -> None:
        self.session.execute(
            update(ResumeVersion)
            .where(
                ResumeVersion.resume_id == resume_id,
                ResumeVersion.id != selected_version_id,
                ResumeVersion.is_primary_active.is_(True),
            )
            .values(is_primary_active=False)
        )
