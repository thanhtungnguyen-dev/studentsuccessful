"""Explicitly submitted application identity/contact facts and partial updates."""

import re
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, StringConstraints, field_validator

from backend.app.schemas.common import StrictBaseModel

Name = Annotated[str, StringConstraints(min_length=1, max_length=100)]
ShortText = Annotated[str, StringConstraints(max_length=100)]
Phone = Annotated[str, StringConstraints(max_length=30)]
Street = Annotated[str, StringConstraints(max_length=255)]
PostalCode = Annotated[str, StringConstraints(max_length=30)]
CountryCode = Annotated[str, StringConstraints(min_length=2, max_length=2)]
WebLink = Annotated[str, StringConstraints(max_length=500)]


class ProfileFields(StrictBaseModel):
    legal_middle_name: ShortText | None = None
    preferred_name: ShortText | None = None
    phone_number: Phone | None = None
    address_street: Street | None = Field(None, description="Street address, including additional lines")
    address_city: ShortText | None = None
    address_state_province: ShortText | None = None
    address_postal_code: PostalCode | None = None
    address_country_code: CountryCode | None = Field(None, description="Explicit two-letter country code")
    linkedin_url: WebLink | None = None
    github_url: WebLink | None = None
    portfolio_url: WebLink | None = None


class ProfileRead(ProfileFields):
    model_config = ConfigDict(from_attributes=True)
    legal_first_name: Name
    legal_last_name: Name


class ProfileUpdate(ProfileFields):
    # A non-nullable type with a default makes omission legal, but explicit null invalid.
    # The service must use exclude_unset=True; defaults are never persisted as a PATCH.
    legal_first_name: Name = Field(default=None, description="Required on first save; cannot clear")
    legal_last_name: Name = Field(default=None, description="Required on first save; cannot clear")

    @field_validator("*", mode="before")
    @classmethod
    def trim_and_clear(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("phone_number")
    @classmethod
    def phone_format(cls, value):
        if value is not None and (
            not re.fullmatch(r"\+?[0-9\s().\-]+(?:\s*(?:x|ext\.?)\s*[0-9]+)?", value, re.IGNORECASE)
            or not 5 <= sum(char.isdigit() for char in value) <= 20
        ):
            raise ValueError("Use a phone number with 5–20 digits and optional dialing punctuation")
        return value

    @field_validator("address_country_code")
    @classmethod
    def country_code(cls, value):
        if value is not None:
            if not re.fullmatch(r"[A-Za-z]{2}", value):
                raise ValueError("Enter an explicit two-letter country code")
            return value.upper()
        return value

    @field_validator("linkedin_url", "github_url", "portfolio_url")
    @classmethod
    def web_url(cls, value):
        if value is not None:
            try:
                url = urlsplit(value)
                valid = (
                    url.scheme in {"http", "https"} and url.hostname
                    and url.username is None and url.password is None
                    and not any(char.isspace() or ord(char) < 32 for char in value)
                    and "\\" not in value
                )
                _ = url.port
            except ValueError:
                valid = False
            if not valid:
                raise ValueError("Use an absolute http or https URL without embedded credentials")
        return value
