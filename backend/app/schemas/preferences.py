"""Explicit preferences, not inferred facts or capability claims."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, field_validator, model_validator

from backend.app.schemas.common import StrictBaseModel

WorkMode = Literal["ON_SITE", "HYBRID", "REMOTE"]
EmploymentType = Literal["INTERNSHIP", "CO_OP", "NEW_GRAD", "PART_TIME"]
PreferenceType = Literal["ROLE", "INDUSTRY", "LOCATION", "COMPANY", "SKILL"]


def normalized_custom(value: str) -> str:
    return " ".join(value.split()).casefold()


class CustomPreference(StrictBaseModel):
    preference_type: PreferenceType
    value: Annotated[str, StringConstraints(min_length=1, max_length=150)]

    @field_validator("value")
    @classmethod
    def nonblank(cls, value):
        normalized = normalized_custom(value)
        if not normalized or len(normalized) > 150:
            raise ValueError("Custom value must be nonblank and normalized length at most 150")
        return value  # Preserve display text; normalization is for uniqueness only.


class Preferences(StrictBaseModel):
    role_ids: list[UUID] = Field(default_factory=list)
    industry_ids: list[UUID] = Field(default_factory=list)
    location_ids: list[UUID] = Field(default_factory=list)
    company_ids: list[UUID] = Field(default_factory=list)
    skill_ids: list[UUID] = Field(default_factory=list)
    work_modes: list[WorkMode] = Field(default_factory=list)
    employment_types: list[EmploymentType] = Field(default_factory=list)
    custom_values: list[CustomPreference] = Field(default_factory=list)

    @field_validator("role_ids", "industry_ids", "location_ids", "company_ids", "skill_ids", "work_modes", "employment_types")
    @classmethod
    def unique_sorted(cls, value):
        return sorted(set(value))

    @model_validator(mode="after")
    def unique_custom(self):
        keys = [(x.preference_type, normalized_custom(x.value)) for x in self.custom_values]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate custom values for the same preference type")
        self.custom_values.sort(key=lambda x: (x.preference_type, normalized_custom(x.value)))
        return self


class CatalogItem(StrictBaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    slug: str | None = None
    is_active: bool | None = None
    category: str | None = None


class CatalogLocation(StrictBaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    country_code: str
    state_province: str | None = None
    city: str
