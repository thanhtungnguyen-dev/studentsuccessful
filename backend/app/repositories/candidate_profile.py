"""Read-only owner-scoped queries for the derived candidate profile."""

from sqlalchemy import func, select

from backend.app.models.portfolio import Project, ProjectCustomSkill, ProjectSkill, UserCustomSkill
from backend.app.models.profile import (
    ApplicationProfile,
    EducationRecord,
    EmploymentRecord,
    WorkAuthorization,
)
from backend.app.models.resume import (
    Resume,
    ResumeEvidenceItem,
    ResumeEvidenceSkill,
    ResumeVersion,
    UserSkill,
)
from backend.app.models.taxonomy import Skill
from backend.app.repositories.portfolio import PortfolioRepository
from backend.app.repositories.preferences import PreferencesRepository


class CandidateProfileRepository:
    """Queries only rows belonging to the supplied authenticated owner; never commits."""

    def __init__(self, session):
        self.session = session

    def profile_for_owner(self, owner):
        return self.session.scalar(
            select(ApplicationProfile).where(ApplicationProfile.user_id == owner)
        )

    def education_for_owner(self, owner):
        return list(
            self.session.scalars(
                select(EducationRecord)
                .where(EducationRecord.user_id == owner)
                .order_by(EducationRecord.created_at, EducationRecord.id)
            )
        )

    def employment_for_owner(self, owner):
        return list(
            self.session.scalars(
                select(EmploymentRecord)
                .where(EmploymentRecord.user_id == owner)
                .order_by(EmploymentRecord.created_at, EmploymentRecord.id)
            )
        )

    def work_authorizations_for_owner(self, owner):
        return list(
            self.session.scalars(
                select(WorkAuthorization)
                .where(WorkAuthorization.user_id == owner)
                .order_by(WorkAuthorization.country_code, WorkAuthorization.id)
            )
        )

    def preferences_for_owner(self, owner):
        return PreferencesRepository(self.session).read(owner)

    def projects_for_owner(self, owner):
        return PortfolioRepository(self.session).projects(owner)

    def confirmed_catalog_skills(self, owner):
        return list(
            self.session.execute(
                select(UserSkill.id, Skill.id, Skill.name, Skill.category)
                .join(Skill, Skill.id == UserSkill.skill_id)
                .where(UserSkill.user_id == owner, UserSkill.confirmed_by_user.is_(True))
                .order_by(func.lower(Skill.name), Skill.id, UserSkill.id)
            )
        )

    def project_catalog_skills(self, owner):
        return list(
            self.session.execute(
                select(Skill.id, Skill.name, Skill.category, Project.id, Project.title)
                .select_from(ProjectSkill)
                .join(Project, Project.id == ProjectSkill.project_id)
                .join(Skill, Skill.id == ProjectSkill.skill_id)
                .where(Project.user_id == owner)
                .order_by(func.lower(Skill.name), Skill.id, func.lower(Project.title), Project.id)
            )
        )

    def resume_skill_sources(self, owner):
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
                .where(Resume.user_id == owner)
                .order_by(
                    func.lower(Skill.name),
                    Skill.id,
                    func.lower(Resume.title),
                    Resume.id,
                    ResumeVersion.version_number,
                    ResumeVersion.id,
                    ResumeEvidenceItem.ordinal,
                    ResumeEvidenceItem.id,
                )
            )
        )

    def evidence_for_owner(self, owner):
        return list(
            self.session.execute(
                select(
                    Resume.id,
                    Resume.title,
                    ResumeVersion.id,
                    ResumeVersion.version_number,
                    ResumeEvidenceItem.id,
                    ResumeEvidenceItem.ordinal,
                    ResumeEvidenceItem.category,
                    ResumeEvidenceItem.section_header,
                    ResumeEvidenceItem.bullet_text,
                )
                .select_from(ResumeEvidenceItem)
                .join(ResumeVersion, ResumeVersion.id == ResumeEvidenceItem.resume_version_id)
                .join(Resume, Resume.id == ResumeVersion.resume_id)
                .where(Resume.user_id == owner)
                .order_by(
                    func.lower(Resume.title),
                    Resume.id,
                    ResumeVersion.version_number,
                    ResumeVersion.id,
                    ResumeEvidenceItem.ordinal,
                    ResumeEvidenceItem.id,
                )
            )
        )

    def evidence_recognized_skills_for_owner(self, owner):
        return list(
            self.session.execute(
                select(
                    ResumeEvidenceItem.id,
                    Skill.id,
                    Skill.name,
                    ResumeEvidenceSkill.parser_confidence,
                )
                .select_from(ResumeEvidenceSkill)
                .join(ResumeEvidenceItem, ResumeEvidenceItem.id == ResumeEvidenceSkill.evidence_item_id)
                .join(ResumeVersion, ResumeVersion.id == ResumeEvidenceItem.resume_version_id)
                .join(Resume, Resume.id == ResumeVersion.resume_id)
                .join(Skill, Skill.id == ResumeEvidenceSkill.skill_id)
                .where(Resume.user_id == owner)
                .order_by(
                    ResumeEvidenceItem.id,
                    func.lower(Skill.name),
                    Skill.id,
                )
            )
        )

    def custom_skill_sources(self, owner):
        confirmed = list(
            self.session.execute(
                select(UserCustomSkill.id, UserCustomSkill.value, UserCustomSkill.normalized_value)
                .where(UserCustomSkill.user_id == owner)
                .order_by(UserCustomSkill.normalized_value, UserCustomSkill.id)
            )
        )
        project = list(
            self.session.execute(
                select(
                    ProjectCustomSkill.id,
                    ProjectCustomSkill.value,
                    ProjectCustomSkill.normalized_value,
                    Project.id,
                    Project.title,
                )
                .select_from(ProjectCustomSkill)
                .join(Project, Project.id == ProjectCustomSkill.project_id)
                .where(Project.user_id == owner)
                .order_by(
                    ProjectCustomSkill.normalized_value,
                    func.lower(Project.title),
                    Project.id,
                    ProjectCustomSkill.id,
                )
            )
        )
        return confirmed, project
