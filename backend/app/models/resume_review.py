"""User-owned, immutable-on-finalization resume tailoring review snapshots."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.app.models.base import Base, generate_uuid, utc_now


class ResumeTailoringReview(Base):
    """A saved Phase 16 draft snapshot for one user, job, and resume version."""

    __tablename__ = "resume_tailoring_reviews"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("normalized_jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_resume_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("resume_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    job_title_snapshot = Column(String(200), nullable=False)
    company_name_snapshot = Column(String(150), nullable=False)
    resume_title_snapshot = Column(String(150), nullable=False)
    resume_version_number_snapshot = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="DRAFT", server_default=text("'DRAFT'"))
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
    finalized_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "job_id",
            "source_resume_version_id",
            name="uq_resume_tailoring_review_user_job_version",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'FINALIZED')", name="ck_resume_tailoring_review_status"
        ),
        CheckConstraint(
            "resume_version_number_snapshot > 0",
            name="ck_resume_tailoring_review_version_number",
        ),
        CheckConstraint(
            "(status = 'DRAFT' AND finalized_at IS NULL) OR "
            "(status = 'FINALIZED' AND finalized_at IS NOT NULL)",
            name="ck_resume_tailoring_review_finalization",
        ),
        Index("idx_resume_tailoring_reviews_user", "user_id"),
        Index(
            "idx_resume_tailoring_reviews_job_version",
            "job_id",
            "source_resume_version_id",
        ),
    )


class ResumeTailoringReviewItem(Base):
    """A source-cited system draft plus separate user review choices and wording."""

    __tablename__ = "resume_tailoring_review_items"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    review_id = Column(
        UUID(as_uuid=True),
        ForeignKey("resume_tailoring_reviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal = Column(Integer, nullable=False)
    category = Column(String(20), nullable=False)
    action = Column(String(50), nullable=False)
    requirement_id = Column(UUID(as_uuid=True), nullable=False)
    requirement_name = Column(String(100), nullable=False)
    importance = Column(String(50), nullable=True)
    requirement_description = Column(Text, nullable=True)
    original_draft_text = Column(String(300), nullable=False)
    reason = Column(Text, nullable=False)
    limitation = Column(Text, nullable=False)
    provenance = Column(JSONB, nullable=False)
    decision = Column(
        String(20), nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    user_edited_text = Column(Text, nullable=True)
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
        UniqueConstraint("review_id", "ordinal", name="uq_resume_tailoring_review_item_ordinal"),
        CheckConstraint("ordinal >= 0", name="ck_resume_tailoring_review_item_ordinal"),
        CheckConstraint(
            "category IN ('SKILL', 'EDUCATION', 'ELIGIBILITY')",
            name="ck_resume_tailoring_review_item_category",
        ),
        CheckConstraint(
            "action = 'CONSIDER_ADDING_EXISTING_EVIDENCE'",
            name="ck_resume_tailoring_review_item_action",
        ),
        CheckConstraint(
            "char_length(btrim(requirement_name)) > 0",
            name="ck_resume_tailoring_review_item_requirement_name",
        ),
        CheckConstraint(
            "char_length(btrim(original_draft_text)) > 0",
            name="ck_resume_tailoring_review_item_original_draft",
        ),
        CheckConstraint(
            "char_length(btrim(reason)) > 0",
            name="ck_resume_tailoring_review_item_reason",
        ),
        CheckConstraint(
            "char_length(btrim(limitation)) > 0",
            name="ck_resume_tailoring_review_item_limitation",
        ),
        CheckConstraint(
            "jsonb_typeof(provenance) = 'array' AND jsonb_array_length(provenance) > 0",
            name="ck_resume_tailoring_review_item_provenance",
        ),
        CheckConstraint(
            "decision IN ('PENDING', 'ACCEPTED', 'REJECTED')",
            name="ck_resume_tailoring_review_item_decision",
        ),
        CheckConstraint(
            "user_edited_text IS NULL OR "
            "(char_length(btrim(user_edited_text)) BETWEEN 1 AND 1000)",
            name="ck_resume_tailoring_review_item_user_text",
        ),
        Index("idx_resume_tailoring_review_items_review", "review_id"),
        Index("idx_resume_tailoring_review_items_decision", "review_id", "decision"),
    )


__all__ = ["ResumeTailoringReview", "ResumeTailoringReviewItem"]
