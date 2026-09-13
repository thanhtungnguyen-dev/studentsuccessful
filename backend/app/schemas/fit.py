"""Derived, explainable candidate-fit contracts with no score or prediction."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from backend.app.schemas.candidate_profile import CandidateSkillSourceRead
from backend.app.schemas.common import StrictBaseModel


class FitRequirementRead(StrictBaseModel):
    """One job requirement and the recorded evidence, if any.

    For ``SKILL`` requirements, ``requirement_id`` is the canonical catalog
    ``skill_id``. It is the same identifier used for exact evidence matching.
    """

    category: Literal["SKILL", "EDUCATION", "ELIGIBILITY"]
    requirement_id: UUID
    name: str = Field(min_length=1)
    importance: str | None = None
    description: str | None = None
    explanation: str = Field(min_length=1)
    limitation: str = Field(min_length=1)
    sources: list[CandidateSkillSourceRead] = Field(default_factory=list)


class FitAnalysisRead(StrictBaseModel):
    """Read-only evidence coverage for one active shared job listing."""

    job_id: UUID
    job_title: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    matched: list[FitRequirementRead] = Field(default_factory=list)
    missing: list[FitRequirementRead] = Field(default_factory=list)
    unknown: list[FitRequirementRead] = Field(default_factory=list)
    limitations: list[str] = Field(min_length=1)
