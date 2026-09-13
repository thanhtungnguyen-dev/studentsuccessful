"""Linked resumes only; server never fetches or parses the external document."""

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, field_validator

from backend.app.schemas.common import StrictBaseModel
from backend.app.schemas.profile import ProfileUpdate


class ArtifactCreate(StrictBaseModel):
    artifact_type: Literal["RESUME"] = "RESUME"
    title: Annotated[str, StringConstraints(min_length=1, max_length=150)]
    external_url: Annotated[str, StringConstraints(min_length=1, max_length=500)]

    @field_validator("title")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Enter a Resume title")
        return value

    @field_validator("external_url")
    @classmethod
    def url(cls, value):
        return ProfileUpdate.web_url(value.strip())


class ArtifactUpdate(ArtifactCreate):
    title: Annotated[str, StringConstraints(min_length=1, max_length=150)] = Field(default=None)
    external_url: Annotated[str, StringConstraints(min_length=1, max_length=500)] = Field(
        default=None
    )


class ArtifactRead(ArtifactCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def utc(cls, value):
        return value.astimezone(timezone.utc)
