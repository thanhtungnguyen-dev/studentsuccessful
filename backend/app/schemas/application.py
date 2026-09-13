"""Private, manual application tracking contracts."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from backend.app.schemas.common import StrictBaseModel

ApplicationStatusValue = Literal["APPLIED", "INTERVIEW", "OFFER", "REJECTED", "WITHDRAWN"]
ApplicationFilterStatus = Literal[
    "ALL", "APPLIED", "INTERVIEW", "OFFER", "REJECTED", "WITHDRAWN"
]


def _clean_note(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


class ApplicationCreate(StrictBaseModel):
    canonical_job_id: UUID
    resume_version_id: UUID | None = None
    applied_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("applied_at")
    @classmethod
    def applied_at_is_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("applied_at must include a timezone")
        return value.astimezone(timezone.utc)

    @field_validator("notes")
    @classmethod
    def notes_are_concise(cls, value: str | None) -> str | None:
        return _clean_note(value)


class ApplicationUpdate(StrictBaseModel):
    expected_version: int = Field(ge=1)
    status: ApplicationStatusValue | None = None
    notes: str | None = Field(default=None, max_length=2000)
    status_note: str | None = Field(default=None, max_length=2000)

    @field_validator("notes", "status_note")
    @classmethod
    def notes_are_concise(cls, value: str | None) -> str | None:
        return _clean_note(value)

    @model_validator(mode="after")
    def has_change(self):
        fields = self.model_fields_set
        if "status" not in fields and "notes" not in fields:
            raise ValueError("Provide a status or notes change")
        if "status_note" in fields and "status" not in fields:
            raise ValueError("status_note requires a status change")
        return self


class ApplicationStatusHistoryRead(StrictBaseModel):
    id: UUID
    previous_status: ApplicationStatusValue | None
    new_status: ApplicationStatusValue
    notes: str | None
    transitioned_at: datetime

    @field_validator("transitioned_at")
    @classmethod
    def utc_transitioned_at(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


class ApplicationRead(StrictBaseModel):
    id: UUID
    canonical_job_id: UUID
    job_title: str
    company_name: str
    application_url: str | None
    job_lifecycle: str | None
    current_status: ApplicationStatusValue
    resume_version_id: UUID | None
    resume_title: str | None
    resume_version_number: int | None
    applied_at: datetime | None
    notes: str | None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    history: list[ApplicationStatusHistoryRead] = Field(default_factory=list)

    @field_validator("applied_at", "created_at", "updated_at")
    @classmethod
    def utc_timestamps(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(timezone.utc) if value is not None else None


class ApplicationListRead(StrictBaseModel):
    items: list[ApplicationRead]
