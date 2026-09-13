"""Read-only, evidence-backed resume improvement plan contracts."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from backend.app.schemas.candidate_profile import CandidateSkillSourceRead
from backend.app.schemas.common import StrictBaseModel

ResumeImprovementAction = Literal[
    "KEEP",
    "CONSIDER_ADDING_EXISTING_EVIDENCE",
    "DO_NOT_CLAIM_WITHOUT_EVIDENCE",
    "MANUAL_REVIEW",
]


class ResumeImprovementActionRead(StrictBaseModel):
    """One conservative action derived from a deterministic requirement outcome."""

    category: Literal["SKILL", "EDUCATION", "ELIGIBILITY"]
    action: ResumeImprovementAction
    requirement_id: UUID
    name: str = Field(min_length=1)
    importance: str | None = None
    description: str | None = None
    reason: str = Field(min_length=1)
    limitation: str = Field(min_length=1)
    sources: list[CandidateSkillSourceRead] = Field(default_factory=list)


class ResumeImprovementPlanRead(StrictBaseModel):
    """Derived actions for one active job and one owned resume version."""

    job_id: UUID
    job_title: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    resume_id: UUID
    resume_title: str = Field(min_length=1)
    resume_version_id: UUID
    resume_version_number: int = Field(ge=1)
    keep: list[ResumeImprovementActionRead] = Field(default_factory=list)
    consider_adding_existing_evidence: list[ResumeImprovementActionRead] = Field(
        default_factory=list
    )
    do_not_claim_without_evidence: list[ResumeImprovementActionRead] = Field(
        default_factory=list
    )
    manual_review: list[ResumeImprovementActionRead] = Field(default_factory=list)
    limitations: list[str] = Field(min_length=1)
