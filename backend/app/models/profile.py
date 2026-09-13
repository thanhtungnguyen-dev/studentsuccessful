"""Application profile, education, employment, authorization, and answer entities."""

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from backend.app.models.base import Base, generate_uuid, utc_now


class ApplicationProfile(Base):
    __tablename__ = "application_profiles"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    legal_first_name = Column(String(100), nullable=False)
    legal_middle_name = Column(String(100), nullable=True)
    legal_last_name = Column(String(100), nullable=False)
    preferred_name = Column(String(100), nullable=True)
    phone_number = Column(String(30), nullable=True)
    address_street = Column(String(255), nullable=True)
    address_city = Column(String(100), nullable=True)
    address_state_province = Column(String(100), nullable=True)
    address_postal_code = Column(String(30), nullable=True)
    address_country_code = Column(CHAR(2), nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    github_url = Column(String(500), nullable=True)
    portfolio_url = Column(String(500), nullable=True)
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


class EducationRecord(Base):
    __tablename__ = "education_records"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    institution_name = Column(String(255), nullable=False)
    degree_level = Column(String(50), nullable=False)
    major = Column(String(150), nullable=False)
    minor = Column(String(150), nullable=True)
    study_year = Column(String(50), nullable=False)
    start_date = Column(Date, nullable=False)
    expected_grad_month = Column(SmallInteger, nullable=False)
    expected_grad_year = Column(SmallInteger, nullable=False)
    gpa_value = Column(Numeric(5, 2), nullable=True)
    gpa_scale = Column(Numeric(5, 2), nullable=True)
    gpa_include_on_apps = Column(
        Boolean, nullable=False, default=False, server_default=text("FALSE")
    )
    is_primary = Column(Boolean, nullable=False, default=False, server_default=text("FALSE"))
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
        Index("idx_education_records_user_id", "user_id"),
        Index("uq_education_primary_user", "user_id", unique=True, postgresql_where=text("is_primary = TRUE")),
        CheckConstraint("(gpa_value IS NULL) = (gpa_scale IS NULL)", name="ck_education_gpa_pair"),
        CheckConstraint("gpa_value >= 0 AND gpa_value <> 'NaN'::numeric", name="ck_education_gpa_nonnegative"),
        CheckConstraint("gpa_scale > 0 AND gpa_scale <> 'NaN'::numeric", name="ck_education_gpa_scale_positive"),
        CheckConstraint("gpa_value <= gpa_scale", name="ck_education_gpa_within_scale"),
        CheckConstraint("NOT gpa_include_on_apps OR (gpa_value IS NOT NULL AND gpa_scale IS NOT NULL)", name="ck_education_gpa_disclosure"),
        CheckConstraint("(EXTRACT(YEAR FROM start_date), EXTRACT(MONTH FROM start_date)) <= (expected_grad_year, expected_grad_month)", name="ck_education_date_order"),
        CheckConstraint("expected_grad_month BETWEEN 1 AND 12", name="ck_education_grad_month"),
        CheckConstraint("expected_grad_year BETWEEN 2000 AND 2100", name="ck_education_grad_year"),
    )


class EmploymentRecord(Base):
    __tablename__ = "employment_records"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    employer_name = Column(String(255), nullable=False)
    job_title = Column(String(150), nullable=False)
    location = Column(String(150), nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    currently_employed = Column(
        Boolean, nullable=False, default=False, server_default=text("FALSE")
    )
    description = Column(Text, nullable=True)
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
        Index("idx_employment_records_user_id", "user_id"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_employment_date_order"),
        CheckConstraint(
            "currently_employed = TRUE OR end_date IS NOT NULL", name="ck_employment_end_date"
        ),
    )


class WorkAuthorization(Base):
    __tablename__ = "work_authorizations"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    country_code = Column(CHAR(2), nullable=False)
    authorization_status = Column(String(50), nullable=False)
    requires_current_sponsorship = Column(
        Boolean, nullable=False, default=False, server_default=text("FALSE")
    )
    requires_future_sponsorship = Column(
        Boolean, nullable=False, default=False, server_default=text("FALSE")
    )
    notes = Column(String(255), nullable=True)
    last_confirmed_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
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
        UniqueConstraint("user_id", "country_code", name="uq_work_auth_user_country"),
        CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="ck_work_authorization_country_code"),
        CheckConstraint("authorization_status IN ('CITIZEN', 'PERMANENT_RESIDENT', 'STUDENT_WORK_AUTHORIZATION', 'TEMPORARY_WORK_AUTHORIZATION', 'OTHER', 'STUDENT_VISA_CPT_OPT', 'WORK_VISA')", name="ck_work_authorization_status"),
    )


class ApplicationAnswer(Base):
    __tablename__ = "application_answers"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    normalized_question_key = Column(String(100), nullable=False)
    original_question_prompt = Column(Text, nullable=False)
    answer_value = Column(Text, nullable=False)
    answer_type = Column(String(30), nullable=False)
    is_sensitive = Column(Boolean, nullable=False, default=False, server_default=text("FALSE"))
    user_approved_for_reuse = Column(
        Boolean, nullable=False, default=False, server_default=text("FALSE")
    )
    last_confirmed_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
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
        UniqueConstraint("user_id", "normalized_question_key", name="uq_app_answer_user_key"),
    )


__all__ = [
    "ApplicationProfile",
    "EducationRecord",
    "EmploymentRecord",
    "WorkAuthorization",
    "ApplicationAnswer",
]
