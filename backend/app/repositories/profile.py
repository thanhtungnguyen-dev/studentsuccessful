"""Persistence scoped to the authenticated profile owner; never commits."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.profile import ApplicationProfile
from backend.app.models.user import User


class ApplicationProfileRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_for_user(self, user_id: UUID) -> ApplicationProfile | None:
        return self.session.scalar(select(ApplicationProfile).where(ApplicationProfile.user_id == user_id))

    def lock_owner(self, user_id: UUID) -> None:
        # Serialize first creation as well as updates without committing in this layer.
        self.session.execute(select(User.id).where(User.id == user_id).with_for_update()).scalar_one()

    def add(self, profile: ApplicationProfile) -> None:
        self.session.add(profile)
