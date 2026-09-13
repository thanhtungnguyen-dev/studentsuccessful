"""Resume documents, versions, evidence items, and confirmed user skills."""

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from backend.app.models.base import Base, generate_uuid, utc_now


class Resume(Base):
    __tablename__ = "resumes"

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
    title = Column(String(150), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (Index("idx_resumes_user_id", "user_id"),)


class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    resume_id = Column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number = Column(Integer, nullable=False, default=1, server_default=text("1"))
    storage_key = Column(String(500), nullable=False)
    file_format = Column(String(10), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    file_hash_sha256 = Column(
        CHAR(64),
        nullable=False,
    )
    is_primary_active = Column(Boolean, nullable=False, default=False, server_default=text("FALSE"))
    parse_status = Column(
        String(30), nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    raw_extracted_text = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint("resume_id", "version_number", name="uq_resume_version_num"),
        CheckConstraint("version_number > 0", name="ck_resume_version_number_positive"),
        CheckConstraint(
            "file_size_bytes > 0 AND file_size_bytes <= 5242880",
            name="ck_resume_version_file_size",
        ),
        CheckConstraint("file_format IN ('PDF', 'DOCX')", name="ck_resume_version_file_format"),
        CheckConstraint(
            "parse_status IN ('PENDING', 'PARSED_SUCCESS', 'PARSE_FAILED', 'USER_MODIFIED')",
            name="ck_resume_version_parse_status",
        ),
        CheckConstraint("file_hash_sha256 ~ '^[0-9a-f]{64}$'", name="ck_resume_version_sha256"),
        CheckConstraint(
            "raw_extracted_text IS NULL OR char_length(raw_extracted_text) <= 262144",
            name="ck_resume_version_raw_text_size",
        ),
        Index(
            "idx_user_primary_resume_version",
            "resume_id",
            unique=True,
            postgresql_where=text("is_primary_active = TRUE"),
        ),
        Index("idx_resume_versions_resume_id", "resume_id"),
        Index("idx_resume_versions_hash", "file_hash_sha256"),
    )


class ResumeEvidenceItem(Base):
    __tablename__ = "resume_evidence_items"

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
    category = Column(String(50), nullable=False)
    section_header = Column(String(150), nullable=True)
    bullet_text = Column(Text, nullable=False)
    ordinal = Column(Integer, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint(
            "category IN ('EDUCATION', 'EXPERIENCE', 'PROJECTS', 'SKILLS', 'OTHER')",
            name="ck_resume_evidence_item_category",
        ),
        CheckConstraint("ordinal >= 0", name="ck_resume_evidence_item_ordinal"),
        CheckConstraint(
            "char_length(btrim(bullet_text)) > 0", name="ck_resume_evidence_item_bullet_text"
        ),
        UniqueConstraint(
            "resume_version_id",
            "ordinal",
            name="uq_resume_evidence_item_version_ordinal",
        ),
        Index("idx_evidence_items_version_id", "resume_version_id"),
        Index(
            "idx_evidence_items_version_ordinal",
            "resume_version_id",
            "ordinal",
        ),
    )


class ResumeEvidenceSkill(Base):
    __tablename__ = "resume_evidence_skills"

    evidence_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("resume_evidence_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    skill_id = Column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    )
    parser_confidence = Column(
        Numeric(3, 2), nullable=False, default=1.00, server_default=text("1.00")
    )

    __table_args__ = (
        CheckConstraint(
            "parser_confidence >= 0 AND parser_confidence <= 1",
            name="ck_resume_evidence_skill_parser_confidence",
        ),
        Index("idx_evidence_skills_skill", "skill_id"),
    )


class UserSkill(Base):
    __tablename__ = "user_skills"

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
    skill_id = Column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    confirmed_by_user = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    source = Column(String(30), nullable=False)
    confirmed_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    user_notes = Column(String(255), nullable=True)
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
        UniqueConstraint("user_id", "skill_id", name="uq_user_skill"),
        Index("idx_user_skills_user", "user_id"),
    )


__all__ = [
    "Resume",
    "ResumeVersion",
    "ResumeEvidenceItem",
    "ResumeEvidenceSkill",
    "UserSkill",
]
