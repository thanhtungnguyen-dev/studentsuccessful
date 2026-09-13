"""Owned artifact queries, no network/file operations or commits."""

from sqlalchemy import select

from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.models.artifact import CareerArtifact


class ArtifactRepository:
    def __init__(self, session):
        self.session = session

    def list(self, owner):
        return list(
            self.session.scalars(
                select(CareerArtifact)
                .where(CareerArtifact.user_id == owner)
                .order_by(CareerArtifact.created_at, CareerArtifact.id)
            )
        )

    def owned(self, owner, id, lock=False):
        query = select(CareerArtifact).where(
            CareerArtifact.user_id == owner, CareerArtifact.id == id
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self.session.scalar(query)
        if row is None:
            raise StudentSuccessfulException(404, "ARTIFACT_NOT_FOUND", "Career artifact not found")
        return row
