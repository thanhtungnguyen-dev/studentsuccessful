"""Read-only queries for exact ResumeVersion-to-job alignment."""

from sqlalchemy import func, select

from backend.app.models.resume import (
    Resume,
    ResumeEvidenceItem,
    ResumeEvidenceSkill,
    ResumeVersion,
)
from backend.app.models.taxonomy import Skill
from backend.app.repositories.candidate_profile import CandidateProfileRepository


class ResumeAlignmentRepository:
    """Owns the owner-scoped source boundary for the derived alignment read model."""

    def __init__(self, session):
        self.session = session
        self._candidate_profile = CandidateProfileRepository(session)

    def owned_version_identity(self, owner, version_id):
        """Return only display-safe identity fields for one owned immutable version."""

        return self.session.execute(
            select(
                Resume.id.label("resume_id"),
                Resume.title.label("resume_title"),
                ResumeVersion.id.label("resume_version_id"),
                ResumeVersion.version_number.label("resume_version_number"),
            )
            .select_from(ResumeVersion)
            .join(Resume, Resume.id == ResumeVersion.resume_id)
            .where(Resume.user_id == owner, ResumeVersion.id == version_id)
        ).one_or_none()

    def selected_resume_skill_sources(self, owner, version_id):
        """Return accepted parser links for exactly one owned version, in source order."""

        return list(
            self.session.execute(
                select(
                    Skill.id,
                    Skill.name,
                    Skill.category,
                    Resume.id,
                    Resume.title,
                    ResumeVersion.id,
                    ResumeVersion.version_number,
                    ResumeEvidenceItem.id,
                    ResumeEvidenceItem.ordinal,
                    ResumeEvidenceItem.category,
                    ResumeEvidenceItem.section_header,
                    ResumeEvidenceSkill.parser_confidence,
                )
                .select_from(ResumeEvidenceSkill)
                .join(ResumeEvidenceItem, ResumeEvidenceItem.id == ResumeEvidenceSkill.evidence_item_id)
                .join(ResumeVersion, ResumeVersion.id == ResumeEvidenceItem.resume_version_id)
                .join(Resume, Resume.id == ResumeVersion.resume_id)
                .join(Skill, Skill.id == ResumeEvidenceSkill.skill_id)
                .where(Resume.user_id == owner, ResumeVersion.id == version_id)
                .order_by(
                    func.lower(Skill.name),
                    Skill.id,
                    ResumeEvidenceItem.ordinal,
                    ResumeEvidenceItem.id,
                )
            )
        )

    def confirmed_catalog_skills(self, owner):
        """Return explicit confirmed catalog skills only; custom text is excluded."""

        return self._candidate_profile.confirmed_catalog_skills(owner)

    def project_catalog_skills(self, owner):
        """Return explicit catalog technologies attached to owned projects only."""

        return self._candidate_profile.project_catalog_skills(owner)
