"""Read-only, evidence-grounded resume tailoring draft contracts."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from backend.app.schemas.candidate_profile import CandidateSkillSourceRead
from backend.app.schemas.common import StrictBaseModel
from backend.app.schemas.resume_plan import ResumeImprovementAction


class ResumeDraftItemRead(StrictBaseModel):
    """One safe drafting outcome for a job requirement and selected resume version."""

    category: Literal["SKILL", "EDUCATION", "ELIGIBILITY"]
    action: ResumeImprovementAction
    requirement_id: UUID
    name: str = Field(min_length=1, max_length=100)
    importance: str | None = None
    description: str | None = None
    reason: str = Field(min_length=1)
    limitation: str = Field(min_length=1)
    sources: list[CandidateSkillSourceRead] = Field(default_factory=list)
    draft_text: str | None = Field(default=None, min_length=1, max_length=300)


class ResumeTailoringDraftRead(StrictBaseModel):
    """Derived, non-persistent resume tailoring content for one owned version."""

    job_id: UUID
    job_title: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    resume_id: UUID
    resume_title: str = Field(min_length=1)
    resume_version_id: UUID
    resume_version_number: int = Field(ge=1)
    keep: list[ResumeDraftItemRead] = Field(default_factory=list)
    draft_suggestions: list[ResumeDraftItemRead] = Field(default_factory=list)
    unsupported: list[ResumeDraftItemRead] = Field(default_factory=list)
    manual_review: list[ResumeDraftItemRead] = Field(default_factory=list)
    limitations: list[str] = Field(min_length=1)
