"""Canonical job-feed, private interaction, and saved-search contracts."""

from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from backend.app.schemas.common import StrictBaseModel


class JobUserStateRead(StrictBaseModel):
    """The authenticated user's private state for one canonical job."""

    job_id: UUID
    saved: bool
    hidden: bool
    viewed_at: datetime | None
    unseen: bool

    @field_validator("viewed_at")
    @classmethod
    def utc_viewed_at(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(timezone.utc) if value is not None else None


class PublicJobRead(StrictBaseModel):
    """A current canonical listing plus the requesting user's private state."""

    id: UUID
    title: str
    description: str | None
    company_id: UUID
    company_name: str
    role_id: UUID
    role_name: str
    employment_type: str
    career_level: str
    work_mode: str
    source_name: str
    application_url: str
    posted_at: datetime | None
    discovered_at: datetime
    first_seen_at: datetime
    last_seen_at: datetime
    last_verified_at: datetime
    canonical_updated_at: datetime
    lifecycle: str
    saved: bool
    hidden: bool
    viewed_at: datetime | None
    unseen: bool
    matched_filters: list[str] = Field(default_factory=list)

    @field_validator(
        "posted_at",
        "discovered_at",
        "first_seen_at",
        "last_seen_at",
        "last_verified_at",
        "canonical_updated_at",
        "viewed_at",
    )
    @classmethod
    def utc_timestamps(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(timezone.utc) if value is not None else None


class PublicJobSearchRead(StrictBaseModel):
    """One deterministic, server-filtered page of canonical jobs."""

    items: list[PublicJobRead]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=50)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class PublicJobDetailRead(PublicJobRead):
    """A shared listing's canonical detail, without private source internals."""

    locations: list[str]
    skill_requirements: list["PublicJobSkillRequirementRead"]
    education_requirements: list["PublicJobEducationRequirementRead"]
    eligibility_requirements: list["PublicJobEligibilityRequirementRead"]


class PublicJobSkillRequirementRead(StrictBaseModel):
    """An explicit canonical skill requirement, not a candidate capability claim."""

    skill_id: UUID
    skill_name: str
    skill_category: str
    importance: str
    description: str | None


class PublicJobEducationRequirementRead(StrictBaseModel):
    """An explicit education requirement from the normalized job record."""

    id: UUID
    degree_level: str
    target_grad_start: date | None
    target_grad_end: date | None


class PublicJobEligibilityRequirementRead(StrictBaseModel):
    """An explicit eligibility requirement without private source evidence."""

    id: UUID
    requirement_type: str
    value: str
    description: str | None


class SavedSearchCriteria(StrictBaseModel):
    """Portable structured criteria for a filter-first job feed."""

    roles: list[str] = Field(default_factory=list, max_length=20)
    countries: list[str] = Field(default_factory=list, max_length=20)
    regions: list[str] = Field(default_factory=list, max_length=20)
    cities: list[str] = Field(default_factory=list, max_length=20)
    job_types: list[str] = Field(default_factory=list, max_length=10)
    work_modes: list[str] = Field(default_factory=list, max_length=10)
    recency: Literal["1h", "24h", "3d", "7d", "all"] = "all"
    keyword: str | None = Field(default=None, max_length=100)
    company: str | None = Field(default=None, max_length=100)
    requirement: str | None = Field(default=None, max_length=100)

    @field_validator(
        "roles",
        "countries",
        "regions",
        "cities",
        "job_types",
        "work_modes",
    )
    @classmethod
    def nonempty_values(cls, values: list[str]) -> list[str]:
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Filter selections must be non-empty strings")
        return values


class SavedJobSearchCreate(StrictBaseModel):
    name: str = Field(min_length=1, max_length=100)
    criteria: SavedSearchCriteria
    alert_mode: Literal["OFF", "INSTANT", "HOURLY_DIGEST", "DAILY_DIGEST"] = "OFF"


class SavedJobSearchUpdate(StrictBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    criteria: SavedSearchCriteria | None = None
    alert_mode: Literal["OFF", "INSTANT", "HOURLY_DIGEST", "DAILY_DIGEST"] | None = None

    @model_validator(mode="after")
    def has_change(self):
        if not self.model_fields_set:
            raise ValueError("Provide a name, criteria, or alert mode to update")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name must be a non-empty string")
        if "criteria" in self.model_fields_set and self.criteria is None:
            raise ValueError("criteria must be an object")
        if "alert_mode" in self.model_fields_set and self.alert_mode is None:
            raise ValueError("alert_mode must be a supported value")
        return self


class SavedJobSearchRead(StrictBaseModel):
    id: UUID
    name: str
    criteria: SavedSearchCriteria
    alert_mode: Literal["OFF", "INSTANT", "HOURLY_DIGEST", "DAILY_DIGEST"]
    alert_enabled_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_validator("alert_enabled_at", "created_at", "updated_at")
    @classmethod
    def utc_timestamps(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(timezone.utc) if value is not None else None


class JobAlertRead(StrictBaseModel):
    """One delivered private alert joined to current canonical job presentation."""

    id: UUID
    canonical_job_id: UUID
    saved_search_id: UUID
    saved_search_name: str
    delivery_mode: Literal["INSTANT", "HOURLY_DIGEST", "DAILY_DIGEST"]
    scheduled_for: datetime
    created_at: datetime
    delivered_at: datetime
    read_at: datetime | None
    title: str
    company_name: str
    employment_type: str
    work_mode: str
    application_url: str
    first_seen_at: datetime
    locations: list[str]

    @field_validator("scheduled_for", "created_at", "delivered_at", "read_at", "first_seen_at")
    @classmethod
    def utc_alert_timestamps(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(timezone.utc) if value is not None else None


class JobAlertInboxRead(StrictBaseModel):
    items: list[JobAlertRead]
    unread_count: int = Field(ge=0)


class JobAlertReadUpdate(StrictBaseModel):
    """Delivered alerts may be marked read; unread is not an alert replay."""

    read: bool

    @model_validator(mode="after")
    def read_must_be_true(self):
        if self.read is not True:
            raise ValueError("read may only be marked true")
        return self


class JobAlertReadState(StrictBaseModel):
    id: UUID
    read_at: datetime

    @field_validator("read_at")
    @classmethod
    def utc_read_at(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


class JobUserStateUpdate(StrictBaseModel):
    """An idempotent patch; viewed may only be marked, never fabricated."""

    saved: bool | None = None
    hidden: bool | None = None
    viewed: bool | None = None

    @model_validator(mode="after")
    def has_change(self):
        if self.saved is None and self.hidden is None and self.viewed is None:
            raise ValueError("Provide saved, hidden, or viewed")
        if self.viewed is False:
            raise ValueError("viewed may only be marked true")
        return self
