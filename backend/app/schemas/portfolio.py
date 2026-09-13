"""Explicit factual claims; never inferred from preferences or project text."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator

from backend.app.schemas.common import StrictBaseModel
from backend.app.schemas.preferences import normalized_custom
from backend.app.schemas.profile import ProfileUpdate, WebLink

SkillText = Annotated[str, StringConstraints(min_length=1, max_length=150)]


class SkillSelection(StrictBaseModel):
    skill_ids: list[UUID] = Field(default_factory=list, max_length=100)
    custom_values: list[SkillText] = Field(default_factory=list, max_length=100)

    @field_validator("skill_ids")
    @classmethod
    def unique_ids(cls, values):
        return sorted(set(values))

    @field_validator("custom_values")
    @classmethod
    def unique_custom(cls, values):
        keys = [normalized_custom(value) for value in values]
        if any(not key or len(key) > 150 for key in keys) or len(set(keys)) != len(keys):
            raise ValueError("Custom skills must be nonblank and unique after normalization")
        return sorted(values, key=normalized_custom)


class ProjectCreate(StrictBaseModel):
    title: Annotated[str, StringConstraints(min_length=1, max_length=150)]
    description: Annotated[str, StringConstraints(max_length=5000)] = Field(default_factory=str)
    technologies: SkillSelection = Field(default_factory=SkillSelection)
    project_url: WebLink | None = None
    repository_url: WebLink | None = None

    @field_validator("title")
    @classmethod
    def title_nonblank(cls, value):
        if not value.strip():
            raise ValueError("Enter a project title")
        return value

    @field_validator("project_url", "repository_url", mode="before")
    @classmethod
    def urls(cls, value):
        if isinstance(value, str):
            value = value.strip() or None
        return ProfileUpdate.web_url(value) if value is None or isinstance(value, str) else value


class ProjectUpdate(ProjectCreate):
    title: Annotated[str, StringConstraints(min_length=1, max_length=150)] = Field(default=None)


class ProjectRead(ProjectCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def utc_timestamps(cls, value):
        return value.astimezone(timezone.utc)
