"""Explicit factual work history, preserving the accepted current/end-date rule."""

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, field_validator, model_validator

from backend.app.schemas.common import StrictBaseModel

Employer = Annotated[str, StringConstraints(min_length=1, max_length=255)]
Title = Annotated[str, StringConstraints(min_length=1, max_length=150)]
Location = Annotated[str, StringConstraints(max_length=150)]


class EmploymentInput(StrictBaseModel):
    location: Location | None = None
    end_date: date | None = None
    description: str | None = None

    @field_validator("employer_name", "job_title", "location", mode="before", check_fields=False)
    @classmethod
    def trim_text(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("description", mode="before")
    @classmethod
    def preserve_description(cls, value):
        # Blank clears; otherwise preserve all user text, whitespace and line breaks.
        return None if isinstance(value, str) and not value.strip() else value


class EmploymentCreate(EmploymentInput):
    employer_name: Employer
    job_title: Title
    start_date: date
    currently_employed: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def consistent_dates(self):
        if not self.currently_employed and self.end_date is None:
            raise ValueError("An end date is required when not currently employed")
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("End date cannot precede start date")
        return self


class EmploymentUpdate(EmploymentInput):
    # Non-nullable facts may be omitted, but cannot be explicitly cleared.
    employer_name: Employer = None
    job_title: Title = None
    start_date: date = None
    currently_employed: bool = Field(default=None, strict=True)


class EmploymentRead(EmploymentCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime
