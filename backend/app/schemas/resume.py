"""Public contracts for managed resume families and immutable uploaded versions."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, field_validator

from backend.app.schemas.common import StrictBaseModel

ResumeTitle = Annotated[str, StringConstraints(min_length=1, max_length=150)]


class ResumeCreate(StrictBaseModel):
    title: ResumeTitle

    @field_validator("title")
    @classmethod
    def title_is_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Enter a resume title")
        return value


class ResumeUpdate(StrictBaseModel):
    title: ResumeTitle = Field(default=None)

    @field_validator("title")
    @classmethod
    def title_is_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Enter a resume title")
        return value


class ResumeRead(ResumeCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


class ResumeVersionRead(StrictBaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    resume_id: UUID
    version_number: int = Field(ge=1)
    file_format: Literal["PDF", "DOCX"]
    file_size_bytes: int = Field(gt=0, le=5 * 1024 * 1024)
    file_hash_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    is_primary_active: bool
    parse_status: Literal["PENDING", "PARSED_SUCCESS", "PARSE_FAILED", "USER_MODIFIED"]
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


class ResumeEvidenceSkillRead(StrictBaseModel):
    """A catalog match detected in one evidence item, never a confirmed user skill."""

    skill_id: UUID
    name: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    parser_confidence: Decimal = Field(ge=0, le=1)


class ResumeEvidenceItemRead(StrictBaseModel):
    """Source-ordered parser evidence belonging to exactly one resume version."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    resume_version_id: UUID
    ordinal: int = Field(ge=0)
    category: Literal["EDUCATION", "EXPERIENCE", "PROJECTS", "SKILLS", "OTHER"]
    section_header: str | None = Field(default=None, max_length=150)
    bullet_text: Annotated[str, StringConstraints(min_length=1)]
    recognized_skills: list[ResumeEvidenceSkillRead] = Field(default_factory=list)


class ResumeExtractedTextRead(StrictBaseModel):
    """Private, normalized text from one owned parsed resume version."""

    raw_extracted_text: str = Field(max_length=262_144)


class ResumePrimaryVersionUpdate(StrictBaseModel):
    version_id: UUID
