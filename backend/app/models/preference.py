"""Career preference and preference join entities."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from backend.app.models.base import Base, generate_uuid, utc_now


class CareerPreference(Base):
    __tablename__ = "career_preferences"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    work_modes = Column(ARRAY(Text), nullable=False, default=list)
    employment_types = Column(ARRAY(Text), nullable=False, default=list)
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint("work_modes <@ ARRAY['ON_SITE','HYBRID','REMOTE']::text[] AND array_position(work_modes, NULL) IS NULL AND (cardinality(work_modes) = 0 OR array_ndims(work_modes) = 1)", name='ck_preferences_work_modes'),
        CheckConstraint("employment_types <@ ARRAY['INTERNSHIP','CO_OP','NEW_GRAD','PART_TIME']::text[] AND array_position(employment_types, NULL) IS NULL AND (cardinality(employment_types) = 0 OR array_ndims(employment_types) = 1)", name='ck_preferences_employment_types'),
    )


class CareerPreferenceCustomValue(Base):
    __tablename__ = "career_preference_custom_values"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    career_preference_id = Column(
        UUID(as_uuid=True), ForeignKey("career_preferences.id", ondelete="CASCADE"), nullable=False
    )
    preference_type = Column(String(30), nullable=False)
    value = Column(String(150), nullable=False)
    normalized_value = Column(String(150), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint("preference_type IN ('ROLE','INDUSTRY','LOCATION','COMPANY','SKILL')", name="ck_custom_preference_type"),
        UniqueConstraint(
            "career_preference_id",
            "preference_type",
            "normalized_value",
            name="uq_custom_pref_val",
        ),
    )


class UserPreferredRole(Base):
    __tablename__ = "user_preferred_roles"

    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id = Column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class UserPreferredIndustry(Base):
    __tablename__ = "user_preferred_industries"

    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    industry_id = Column(
        UUID(as_uuid=True), ForeignKey("industries.id", ondelete="CASCADE"), primary_key=True
    )


class UserPreferredLocation(Base):
    __tablename__ = "user_preferred_locations"

    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    location_id = Column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), primary_key=True
    )


class UserPreferredCompany(Base):
    __tablename__ = "user_preferred_companies"

    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )


class UserPreferredSkill(Base):
    __tablename__ = "user_preferred_skills"

    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id = Column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )


__all__ = [
    "CareerPreference",
    "CareerPreferenceCustomValue",
    "UserPreferredRole",
    "UserPreferredIndustry",
    "UserPreferredLocation",
    "UserPreferredCompany",
    "UserPreferredSkill",
]
