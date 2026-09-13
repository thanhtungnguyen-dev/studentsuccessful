"""Taxonomy entities: roles, skills, aliases, companies, locations, industries."""

from sqlalchemy import (
    CHAR,
    Boolean,
    Column,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from backend.app.models.base import Base, generate_uuid


class Role(Base):
    __tablename__ = "roles"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    name = Column(String(100), nullable=False)
    slug = Column(
        String(100),
        unique=True,
        nullable=False,
    )
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))


class Skill(Base):
    __tablename__ = "skills"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    name = Column(String(100), nullable=False)
    slug = Column(
        String(100),
        unique=True,
        nullable=False,
    )
    category = Column(String(50), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))


class SkillAlias(Base):
    __tablename__ = "skill_aliases"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    skill_id = Column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    alias = Column(String(100), nullable=False)
    normalized_alias = Column(
        String(100),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("skill_id", "normalized_alias", name="uq_skill_alias_normalized"),
        Index("idx_skill_aliases_lookup", "normalized_alias"),
    )


class Company(Base):
    __tablename__ = "companies"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    name = Column(String(150), nullable=False)
    domain = Column(String(150), nullable=True)
    is_verified = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))


class Location(Base):
    __tablename__ = "locations"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    country_code = Column(CHAR(2), nullable=False)
    state_province = Column(String(100), nullable=True)
    city = Column(String(100), nullable=False)


class Industry(Base):
    __tablename__ = "industries"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    name = Column(String(100), nullable=False)
    slug = Column(
        String(100),
        unique=True,
        nullable=False,
    )


__all__ = [
    "Role",
    "Skill",
    "SkillAlias",
    "Company",
    "Location",
    "Industry",
]
