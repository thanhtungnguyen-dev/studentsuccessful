"""Explicit user skills and independent user-owned projects."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from backend.app.models.base import Base, generate_uuid, utc_now


class UserCustomSkill(Base):
    __tablename__ = "user_custom_skills"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    value = Column(String(150), nullable=False)
    normalized_value = Column(String(150), nullable=False)
    __table_args__ = (
        UniqueConstraint("user_id", "normalized_value", name="uq_user_custom_skill"),
        CheckConstraint(
            "length(btrim(value)) > 0 AND length(btrim(normalized_value)) > 0",
            name="ck_user_custom_skill_nonblank",
        ),
    )


class Project(Base):
    __tablename__ = "projects"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=False, default="", server_default=text("''"))
    project_url = Column(String(500), nullable=True)
    repository_url = Column(String(500), nullable=True)
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
        Index("idx_projects_user", "user_id"),
        CheckConstraint("length(btrim(title)) > 0", name="ck_project_title_nonblank"),
        CheckConstraint("length(description) <= 5000", name="ck_project_description_length"),
    )


class ProjectSkill(Base):
    __tablename__ = "project_skills"
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id = Column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True
    )


class ProjectCustomSkill(Base):
    __tablename__ = "project_custom_skills"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    value = Column(String(150), nullable=False)
    normalized_value = Column(String(150), nullable=False)
    __table_args__ = (
        UniqueConstraint("project_id", "normalized_value", name="uq_project_custom_skill"),
        CheckConstraint(
            "length(btrim(value)) > 0 AND length(btrim(normalized_value)) > 0",
            name="ck_project_custom_skill_nonblank",
        ),
    )
