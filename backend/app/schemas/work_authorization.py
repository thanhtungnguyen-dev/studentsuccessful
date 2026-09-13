"""Explicit user-supplied country authorization facts; no legal inference."""
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, field_validator

from backend.app.schemas.common import StrictBaseModel


class AuthorizationStatus(StrEnum):
    CITIZEN = "CITIZEN"
    PERMANENT_RESIDENT = "PERMANENT_RESIDENT"
    STUDENT_WORK_AUTHORIZATION = "STUDENT_WORK_AUTHORIZATION"
    TEMPORARY_WORK_AUTHORIZATION = "TEMPORARY_WORK_AUTHORIZATION"
    OTHER = "OTHER"
    STUDENT_VISA_CPT_OPT = "STUDENT_VISA_CPT_OPT"
    WORK_VISA = "WORK_VISA"


CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$", min_length=2, max_length=2)]
Notes = Annotated[str, StringConstraints(max_length=255)]


class WorkAuthorizationInput(StrictBaseModel):
    notes: Notes | None = None

    @field_validator("country_code", mode="before", check_fields=False)
    @classmethod
    def normalize_country(cls, value):
        if isinstance(value, str):
            value = value.strip()
            # Validate ASCII before uppercasing: e.g. Unicode sharp-s must not become SS.
            if len(value) != 2 or not value.isascii() or not value.isalpha():
                raise ValueError("Country code must be exactly two ASCII letters")
            return value.upper()
        return value

    @field_validator("notes", mode="before")
    @classmethod
    def normalize_notes(cls, value):
        return value.strip() or None if isinstance(value, str) else value


class WorkAuthorizationCreate(WorkAuthorizationInput):
    country_code: CountryCode
    authorization_status: AuthorizationStatus
    requires_current_sponsorship: bool = Field(default=False, strict=True)
    requires_future_sponsorship: bool = Field(default=False, strict=True)


class WorkAuthorizationUpdate(WorkAuthorizationInput):
    country_code: CountryCode = None
    authorization_status: AuthorizationStatus = None
    requires_current_sponsorship: bool = Field(default=None, strict=True)
    requires_future_sponsorship: bool = Field(default=None, strict=True)


class WorkAuthorizationRead(WorkAuthorizationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    last_confirmed_at: datetime
    created_at: datetime
    updated_at: datetime

    @field_validator("last_confirmed_at", "created_at", "updated_at")
    @classmethod
    def serialize_utc(cls, value):
        # PostgreSQL may return its connection timezone; expose a consistent UTC instant.
        return value.astimezone(timezone.utc)
