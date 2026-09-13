"""Read-only candidate profile assembled from explicit facts and resume evidence."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from backend.app.schemas.common import StrictBaseModel
from backend.app.schemas.education import EducationRead
from backend.app.schemas.employment import EmploymentRead
from backend.app.schemas.portfolio import ProjectRead
from backend.app.schemas.preferences import Preferences
from backend.app.schemas.profile import ProfileRead
from backend.app.schemas.work_authorization import WorkAuthorizationRead

CandidateSourceType = Literal["CONFIRMED_BY_USER", "RESUME_EVIDENCE", "PROJECT"]
EvidenceCategory = Literal["EDUCATION", "EXPERIENCE", "PROJECTS", "SKILLS", "OTHER"]


class CandidateSkillSourceRead(StrictBaseModel):
    """One immutable source for a reconciled catalog skill."""

    source_type: CandidateSourceType
    source_id: UUID
    resume_id: UUID | None = None
    resume_title: str | None = None
    resume_version_id: UUID | None = None
    resume_version_number: int | None = Field(default=None, ge=1)
    evidence_ordinal: int | None = Field(default=None, ge=0)
    evidence_category: EvidenceCategory | None = None
    evidence_section_header: str | None = Field(default=None, max_length=150)
    parser_confidence: Decimal | None = Field(default=None, ge=0, le=1)
    project_id: UUID | None = None
    project_title: str | None = None


class CandidateSkillRead(StrictBaseModel):
    """A catalog skill reconciled by exact skill ID, never inferred capability."""

    skill_id: UUID
    name: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=50)
    sources: list[CandidateSkillSourceRead] = Field(min_length=1)


class CandidateResumeEvidenceSkillRead(StrictBaseModel):
    """A parser-recognized catalog skill in one evidence item."""

    skill_id: UUID
    name: str = Field(min_length=1, max_length=100)
    parser_confidence: Decimal = Field(ge=0, le=1)


class CandidateResumeEvidenceRead(StrictBaseModel):
    """Version-scoped parser evidence; source text only, never extracted document text."""

    resume_id: UUID
    resume_title: str = Field(min_length=1, max_length=150)
    resume_version_id: UUID
    resume_version_number: int = Field(ge=1)
    evidence_item_id: UUID
    ordinal: int = Field(ge=0)
    category: EvidenceCategory
    section_header: str | None = Field(default=None, max_length=150)
    bullet_text: str = Field(min_length=1)
    recognized_skills: list[CandidateResumeEvidenceSkillRead] = Field(default_factory=list)


class CandidateCustomSkillSourceRead(StrictBaseModel):
    """Explicit custom skill text from the user or a project."""

    source_type: Literal["CONFIRMED_BY_USER", "PROJECT"]
    source_id: UUID
    project_id: UUID | None = None
    project_title: str | None = None


class CandidateCustomSkillRead(StrictBaseModel):
    """Exact normalized custom text is grouped without catalog matching or inference."""

    name: str = Field(min_length=1, max_length=150)
    sources: list[CandidateCustomSkillSourceRead] = Field(min_length=1)


class CandidateProfileRead(StrictBaseModel):
    """The authenticated user's derived profile view. It creates no new facts."""

    facts_source: Literal["ADDED_BY_USER"] = "ADDED_BY_USER"
    profile: ProfileRead | None = None
    education: list[EducationRead] = Field(default_factory=list)
    employment: list[EmploymentRead] = Field(default_factory=list)
    work_authorizations: list[WorkAuthorizationRead] = Field(default_factory=list)
    preferences: Preferences = Field(default_factory=Preferences)
    projects: list[ProjectRead] = Field(default_factory=list)
    skills: list[CandidateSkillRead] = Field(default_factory=list)
    custom_skills: list[CandidateCustomSkillRead] = Field(default_factory=list)
    resume_evidence: list[CandidateResumeEvidenceRead] = Field(default_factory=list)
