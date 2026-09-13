"""Authentication request and response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, EmailStr, Field, field_validator

from backend.app.core.security import normalize_email
from backend.app.schemas.common import StrictBaseModel


class RegisterRequest(StrictBaseModel):
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(
        ..., min_length=8, max_length=128, description="User password (min 8 chars)"
    )

    @field_validator("email", mode="before")
    @classmethod
    def clean_email(cls, v: str) -> str:
        if isinstance(v, str):
            return normalize_email(v)
        return v


class LoginRequest(StrictBaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=1, max_length=128, description="User password")

    @field_validator("email", mode="before")
    @classmethod
    def clean_email(cls, v: str) -> str:
        if isinstance(v, str):
            return normalize_email(v)
        return v


class UserResponse(StrictBaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID = Field(..., description="User UUID")
    email: str = Field(..., description="Normalized user email")
    is_active: bool = Field(..., description="Active status")
    created_at: datetime = Field(..., description="Timestamp created")
    onboarding_completed_at: datetime | None = Field(..., description="First explicit onboarding completion, or null when incomplete")


class CompleteOnboardingRequest(StrictBaseModel):
    """No user ID or client timestamp is accepted."""


class AuthResponse(StrictBaseModel):
    user: UserResponse
    csrf_token: str = Field(..., description="Raw CSRF token to be included in X-CSRF-Token header")


class LogoutResponse(StrictBaseModel):
    message: str = Field(default="Successfully logged out")


__all__ = [
    "RegisterRequest",
    "LoginRequest",
    "UserResponse",
    "AuthResponse",
    "LogoutResponse",
]
