"""User account and authentication session entities matching approved Phase 3.1 schema."""

from sqlalchemy import (
    CHAR,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from backend.app.models.base import Base, generate_uuid, utc_now


class User(Base):
    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    email = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    onboarding_completed_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
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

    __table_args__ = (Index("idx_users_email_lower", func.lower(email), unique=True),)


class UserSession(Base):
    __tablename__ = "user_sessions"

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
    session_token_hash = Column(
        CHAR(64),
        unique=True,
        nullable=False,
    )
    csrf_token_hash = Column(CHAR(64), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    last_seen_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_user_sessions_user", "user_id"),)


__all__ = ["User", "UserSession"]
