"""All SQLAlchemy models registered under Base.metadata."""

from backend.app.models.application import (
    Application,
    ApplicationStatus,
    ApplicationStatusHistory,
    ResumeEvaluation,
)
from backend.app.models.artifact import CareerArtifact
from backend.app.models.base import Base, generate_uuid
from backend.app.models.job import (
    JobAlert,
    JobAlertDeliveryState,
    JobEducationRequirement,
    JobEligibilityRequirement,
    JobIndustry,
    JobLifecycle,
    JobLocation,
    JobSkillRequirement,
    JobSourceAuthority,
    JobSourceObservation,
    JobSourceRecord,
    LiveSourceHealth,
    LiveSourceState,
    NormalizedJob,
    RawJobSnapshot,
    SavedJobSearch,
    SavedSearchAlertMode,
    UserJobState,
)
from backend.app.models.operations import WorkerHeartbeat, WorkerRuntimeState
from backend.app.models.portfolio import Project, ProjectCustomSkill, ProjectSkill, UserCustomSkill
from backend.app.models.preference import (
    CareerPreference,
    CareerPreferenceCustomValue,
    UserPreferredCompany,
    UserPreferredIndustry,
    UserPreferredLocation,
    UserPreferredRole,
    UserPreferredSkill,
)
from backend.app.models.profile import (
    ApplicationAnswer,
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
from backend.app.models.resume_review import ResumeTailoringReview, ResumeTailoringReviewItem
from backend.app.models.taxonomy import (
    Company,
    Industry,
    Location,
    Role,
    Skill,
    SkillAlias,
)
from backend.app.models.user import User, UserSession

__all__ = [
    "Project", "ProjectSkill", "ProjectCustomSkill", "UserCustomSkill",
    "CareerArtifact",
    "WorkerHeartbeat",
    "WorkerRuntimeState",
    "Base",
    "generate_uuid",
    # User & Session
    "User",
    "UserSession",
    # Profile & Factual Records
    "ApplicationProfile",
    "EducationRecord",
    "EmploymentRecord",
    "WorkAuthorization",
    "ApplicationAnswer",
    # Taxonomy
    "Role",
    "Skill",
    "SkillAlias",
    "Company",
    "Location",
    "Industry",
    # Career Preferences
    "CareerPreference",
    "CareerPreferenceCustomValue",
    "UserPreferredRole",
    "UserPreferredIndustry",
    "UserPreferredLocation",
    "UserPreferredCompany",
    "UserPreferredSkill",
    # Resumes & Skills
    "Resume",
    "ResumeVersion",
    "ResumeEvidenceItem",
    "ResumeEvidenceSkill",
    "UserSkill",
    "ResumeTailoringReview",
    "ResumeTailoringReviewItem",
    # Jobs
    "JobSourceRecord",
    "JobAlert",
    "JobAlertDeliveryState",
    "JobLifecycle",
    "JobSourceAuthority",
    "JobSourceObservation",
    "LiveSourceHealth",
    "LiveSourceState",
    "RawJobSnapshot",
    "NormalizedJob",
    "UserJobState",
    "SavedJobSearch",
    "SavedSearchAlertMode",
    "JobIndustry",
    "JobLocation",
    "JobSkillRequirement",
    "JobEducationRequirement",
    "JobEligibilityRequirement",
    # Applications & Evaluations
    "ResumeEvaluation",
    "Application",
    "ApplicationStatus",
    "ApplicationStatusHistory",
]
