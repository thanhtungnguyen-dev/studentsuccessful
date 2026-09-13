"""Strict, transport-independent external facts accepted by job ingestion."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import ConfigDict, Field

from backend.app.schemas.common import StrictBaseModel


class _ExternalDTO(StrictBaseModel):
    """Forbid vendor-specific or accidental raw payload fields at the boundary."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ExternalJobSkillRequirement(_ExternalDTO):
    skill: str
    importance: str = "REQUIRED"
    description: str | None = None


class ExternalJobEducationRequirement(_ExternalDTO):
    degree_level: str
    target_grad_start: date | None = None
    target_grad_end: date | None = None


class ExternalJobEligibilityRequirement(_ExternalDTO):
    requirement_type: str
    value: str
    description: str | None = None


class ExternalJobDTO(_ExternalDTO):
    """Whitelisted input for an external listing.

    `raw_payload` and hashes are purposefully absent.  The ingestion service
    constructs both from the validated, normalized facts it owns.
    """

    adapter_key: str
    external_id: str
    source_url: str
    application_url: str
    company: str
    title: str
    role: str
    employment_type: str
    career_level: str = "UNSPECIFIED"
    work_mode: str = "UNSPECIFIED"
    description: str | None = None
    posted_at: datetime | None = None
    source_updated_at: datetime | None = None
    source_status: Literal["ACTIVE", "CLOSED"] = "ACTIVE"
    locations: tuple[str, ...] = Field(default_factory=tuple)
    skills: tuple[ExternalJobSkillRequirement, ...] = Field(default_factory=tuple)
    education_requirements: tuple[ExternalJobEducationRequirement, ...] = Field(
        default_factory=tuple
    )
    eligibility_requirements: tuple[ExternalJobEligibilityRequirement, ...] = Field(
        default_factory=tuple
    )
    industries: tuple[str, ...] = Field(default_factory=tuple)
