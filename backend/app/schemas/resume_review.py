"""Persistent, user-owned reviews of safe Phase 16 draft suggestions."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from backend.app.schemas.candidate_profile import CandidateSkillSourceRead
from backend.app.schemas.common import StrictBaseModel
from backend.app.schemas.resume_plan import ResumeImprovementAction

ReviewStatus = Literal["DRAFT", "FINALIZED"]
ReviewDecision = Literal["PENDING", "ACCEPTED", "REJECTED"]


class ResumeTailoringReviewCreate(StrictBaseModel):
    """Select an owned immutable resume version for a new review snapshot."""

    resume_version_id: UUID


class ResumeTailoringReviewItemUpdate(StrictBaseModel):
    """A user decision and/or user-authored wording, never evidence input."""

    decision: ReviewDecision | None = None
    user_edited_text: str | None = Field(default=None, max_length=1000)

    @field_validator("user_edited_text")
    @classmethod
    def normalize_user_edited_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("user_edited_text must contain visible text")
        return normalized

    @model_validator(mode="after")
    def require_a_change(self):
        fields = self.model_fields_set
        if not fields.intersection({"decision", "user_edited_text"}):
            raise ValueError("Provide a decision or user_edited_text")
        if "decision" in fields and self.decision is None:
            raise ValueError("decision must be ACCEPTED, REJECTED, or PENDING")
        return self


class ResumeTailoringReviewItemRead(StrictBaseModel):
    """Immutable system snapshot plus the user's separately stored review state."""

    id: UUID
    ordinal: int = Field(ge=0)
    category: Literal["SKILL", "EDUCATION", "ELIGIBILITY"]
    action: ResumeImprovementAction
    requirement_id: UUID
    name: str = Field(min_length=1, max_length=100)
    importance: str | None = None
    description: str | None = None
    original_draft_text: str = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=1)
    limitation: str = Field(min_length=1)
    provenance: list[CandidateSkillSourceRead] = Field(min_length=1)
    decision: ReviewDecision
    user_edited_text: str | None = Field(default=None, min_length=1, max_length=1000)
    created_at: datetime
    updated_at: datetime


class ResumeTailoringReviewRead(StrictBaseModel):
    """A stable saved review for a job and selected resume version."""

    id: UUID
    status: ReviewStatus
    job_id: UUID
    job_title: str = Field(min_length=1, max_length=200)
    company_name: str = Field(min_length=1, max_length=150)
    source_resume_version_id: UUID
    resume_title: str = Field(min_length=1, max_length=150)
    resume_version_number: int = Field(ge=1)
    items: list[ResumeTailoringReviewItemRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    finalized_at: datetime | None = None
