"""Read-only, provenance-preserving skill gap analysis contracts."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from backend.app.schemas.candidate_profile import CandidateSkillSourceRead
from backend.app.schemas.common import StrictBaseModel

SkillGapClassification = Literal[
    "COVERED",
    "RESUME_PRESENTATION_GAP",
    "CANDIDATE_EVIDENCE_GAP",
    "UNKNOWN_UNASSESSED",
]


class SkillGapRequirementRead(StrictBaseModel):
    """One explicit requirement grouped by deterministic recorded evidence."""

    category: Literal["SKILL", "EDUCATION", "ELIGIBILITY"]
    classification: SkillGapClassification
    requirement_id: UUID
    name: str = Field(min_length=1)
    importance: str | None = None
    description: str | None = None
    explanation: str = Field(min_length=1)
    limitation: str = Field(min_length=1)
    sources: list[CandidateSkillSourceRead] = Field(default_factory=list)


class SkillGapAnalysisRead(StrictBaseModel):
    """Derived gaps for one active job and one owned resume version."""

    job_id: UUID
    job_title: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    resume_id: UUID
    resume_title: str = Field(min_length=1)
    resume_version_id: UUID
    resume_version_number: int = Field(ge=1)
    covered: list[SkillGapRequirementRead] = Field(default_factory=list)
    resume_presentation_gaps: list[SkillGapRequirementRead] = Field(default_factory=list)
    candidate_evidence_gaps: list[SkillGapRequirementRead] = Field(default_factory=list)
    unknown: list[SkillGapRequirementRead] = Field(default_factory=list)
    limitations: list[str] = Field(min_length=1)
