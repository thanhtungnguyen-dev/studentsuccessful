"""User-managed external resume references, independent of structured facts."""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID

from backend.app.models.base import Base, generate_uuid, utc_now


class CareerArtifact(Base):
    __tablename__ = "career_artifacts"
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid,
        server_default=text("gen_random_uuid()"),
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    artifact_type = Column(String(20), nullable=False)
    title = Column(String(150), nullable=False)
    external_url = Column(String(500), nullable=False)
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
        Index("idx_career_artifacts_user", "user_id"),
        CheckConstraint("artifact_type = 'RESUME'", name="ck_artifact_type"),
        CheckConstraint("length(btrim(title)) > 0", name="ck_artifact_title"),
        CheckConstraint("external_url ~ '^https?://'", name="ck_artifact_url_scheme"),
    )
