"""Read-only, version-scoped resume alignment contracts."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from backend.app.schemas.candidate_profile import CandidateSkillSourceRead
from backend.app.schemas.common import StrictBaseModel


class ResumeAlignmentRequirementRead(StrictBaseModel):
    """One explicit job requirement grouped by deterministic recorded evidence."""

    category: Literal["SKILL", "EDUCATION", "ELIGIBILITY"]
    requirement_id: UUID
    name: str = Field(min_length=1)
    importance: str | None = None
    description: str | None = None
    explanation: str = Field(min_length=1)
    limitation: str = Field(min_length=1)
    sources: list[CandidateSkillSourceRead] = Field(default_factory=list)


class ResumeAlignmentRead(StrictBaseModel):
    """Derived evidence coverage for one owned resume version and one active job."""

    job_id: UUID
    job_title: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    resume_id: UUID
    resume_title: str = Field(min_length=1)
    resume_version_id: UUID
    resume_version_number: int = Field(ge=1)
    shown_on_resume: list[ResumeAlignmentRequirementRead] = Field(default_factory=list)
    candidate_evidence_not_shown: list[ResumeAlignmentRequirementRead] = Field(
        default_factory=list
    )
    no_recorded_evidence: list[ResumeAlignmentRequirementRead] = Field(default_factory=list)
    unknown_unassessed: list[ResumeAlignmentRequirementRead] = Field(default_factory=list)
    limitations: list[str] = Field(min_length=1)
