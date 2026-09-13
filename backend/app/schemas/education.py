"""User-submitted education facts; GPA stays Decimal on its native scale."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    field_validator,
    model_validator,
)

from backend.app.schemas.common import StrictBaseModel

DegreeLevel = Literal["BS", "BA", "MS", "PHD", "ASSOCIATES", "OTHER"]
StudyYear = Literal["YEAR_1", "YEAR_2", "YEAR_3", "YEAR_4", "YEAR_5_PLUS", "GRADUATE", "OTHER"]
Institution = Annotated[str, StringConstraints(min_length=1, max_length=255)]
Subject = Annotated[str, StringConstraints(min_length=1, max_length=150)]
GpaValue = Annotated[Decimal, Field(ge=0, max_digits=5, decimal_places=2, allow_inf_nan=False)]
GpaScale = Annotated[Decimal, Field(gt=0, max_digits=5, decimal_places=2, allow_inf_nan=False)]
GradMonth = Annotated[int, Field(ge=1, le=12, strict=True)]
GradYear = Annotated[int, Field(ge=2000, le=2100, strict=True)]


class EducationInput(StrictBaseModel):
    minor: Subject | None = None
    gpa_value: GpaValue | None = None
    gpa_scale: GpaScale | None = None
    gpa_include_on_apps: bool = Field(default=False, strict=True)
    is_primary: bool = Field(default=False, strict=True)

    @field_validator("institution_name", "major", "minor", mode="before", check_fields=False)
    @classmethod
    def trim_text(cls, value):
        return value.strip() or None if isinstance(value, str) else value


class EducationCreate(EducationInput):
    institution_name: Institution
    degree_level: DegreeLevel
    major: Subject
    study_year: StudyYear
    start_date: date
    expected_grad_month: GradMonth
    expected_grad_year: GradYear

    @model_validator(mode="after")
    def consistent_facts(self):
        if (self.gpa_value is None) != (self.gpa_scale is None):
            raise ValueError("GPA value and scale must both be supplied or both cleared")
        if self.gpa_value is not None and self.gpa_value > self.gpa_scale:
            raise ValueError("GPA value cannot exceed its native scale")
        if self.gpa_include_on_apps and self.gpa_value is None:
            raise ValueError("Including GPA on applications requires a complete GPA pair")
        if (self.start_date.year, self.start_date.month) > (self.expected_grad_year, self.expected_grad_month):
            raise ValueError("Expected graduation month/year cannot precede the start month/year")
        return self


class EducationUpdate(EducationInput):
    gpa_include_on_apps: bool = Field(default=None, strict=True)
    is_primary: bool = Field(default=None, strict=True)
    # Omission is permitted; explicit null is rejected for non-nullable facts.
    # Only exclude_unset=True may be merged with the stored record.
    institution_name: Institution = None
    degree_level: DegreeLevel = None
    major: Subject = None
    study_year: StudyYear = None
    start_date: date = None
    expected_grad_month: GradMonth = None
    expected_grad_year: GradYear = None


class EducationRead(EducationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime

    @field_serializer("gpa_value", "gpa_scale")
    def decimal_text(self, value: Decimal | None) -> str | None:
        return format(value, ".2f") if value is not None else None
