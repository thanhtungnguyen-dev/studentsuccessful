"""Application tracking, status history, and resume evaluation entities."""

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from backend.app.models.base import Base, generate_uuid, utc_now


class ApplicationStatus:
    """Manual application-process states; Save/Hide remain separate job state."""

    APPLIED = "APPLIED"
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    ALL = (APPLIED, INTERVIEW, OFFER, REJECTED, WITHDRAWN)


class ResumeEvaluation(Base):
    __tablename__ = "resume_evaluations"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    resume_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("resume_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    evaluation_type = Column(String(50), nullable=False)
    target_role_id = Column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="SET NULL"), nullable=True
    )
    target_job_id = Column(
        UUID(as_uuid=True), ForeignKey("normalized_jobs.id", ondelete="SET NULL"), nullable=True
    )
    rubric_version = Column(String(50), nullable=False)
    overall_score = Column(SmallInteger, nullable=False)
    category_scores = Column(JSONB, nullable=False)
    itemized_reasons = Column(ARRAY(Text), nullable=False, default=list)
    suggested_improvements = Column(ARRAY(Text), nullable=False, default=list)
    bullet_analysis_detail = Column(JSONB, nullable=True)
    evaluated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("idx_evaluations_resume_version", "resume_version_id"),
        CheckConstraint("overall_score BETWEEN 0 AND 100", name="ck_evaluation_score"),
    )


class Application(Base):
    __tablename__ = "applications"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(
        UUID(as_uuid=True), ForeignKey("normalized_jobs.id", ondelete="RESTRICT"), nullable=False
    )
    resume_version_id = Column(
        UUID(as_uuid=True), ForeignKey("resume_versions.id", ondelete="RESTRICT"), nullable=True
    )
    resume_title_snapshot = Column(String(150), nullable=True)
    resume_hash_snapshot = Column(CHAR(64), nullable=True)
    job_title_snapshot = Column(String(200), nullable=True)
    company_name_snapshot = Column(String(150), nullable=True)
    current_status = Column(
        String(50),
        nullable=False,
        default=ApplicationStatus.APPLIED,
        server_default=text("'APPLIED'"),
    )
    version = Column(Integer, nullable=False, default=1, server_default=text("1"))
    applied_at = Column(DateTime(timezone=True), nullable=True)
    deadline_at = Column(DateTime(timezone=True), nullable=True)
    next_follow_up_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
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
        UniqueConstraint("user_id", "job_id", name="uq_app_user_job"),
        Index("idx_applications_user_status", "user_id", "current_status"),
        Index("idx_applications_user_followup", "user_id", "next_follow_up_at"),
        Index("idx_applications_owner_updated", "user_id", "updated_at", "id"),
        CheckConstraint("version >= 1", name="ck_application_version"),
        CheckConstraint(
            "current_status IN ('APPLIED', 'INTERVIEW', 'OFFER', 'REJECTED', 'WITHDRAWN')",
            name="ck_application_current_status",
        ),
        CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 2000",
            name="ck_application_notes_length",
        ),
    )


class ApplicationStatusHistory(Base):
    __tablename__ = "application_status_histories"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    application_id = Column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    previous_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=False)
    rejection_stage = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    transitioned_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("idx_app_history_app_transitioned", "application_id", "transitioned_at"),
        CheckConstraint(
            "new_status IN ('APPLIED', 'INTERVIEW', 'OFFER', 'REJECTED', 'WITHDRAWN')",
            name="ck_application_history_new_status",
        ),
        CheckConstraint(
            "previous_status IS NULL OR previous_status IN "
            "('APPLIED', 'INTERVIEW', 'OFFER', 'REJECTED', 'WITHDRAWN')",
            name="ck_application_history_previous_status",
        ),
        CheckConstraint(
            "previous_status IS NULL OR previous_status <> new_status",
            name="ck_application_history_status_change",
        ),
        CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 2000",
            name="ck_application_history_notes_length",
        ),
    )


__all__ = [
    "ResumeEvaluation",
    "Application",
    "ApplicationStatus",
    "ApplicationStatusHistory",
]
