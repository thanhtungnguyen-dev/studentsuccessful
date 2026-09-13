"""Owner-scoped education persistence without transaction decisions."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.models.profile import EducationRecord
from backend.app.models.user import User


class EducationRepository:
    def __init__(self, session: Session):
        self.session = session

    def lock_owner(self, user_id: UUID) -> None:
        self.session.execute(select(User.id).where(User.id == user_id).with_for_update()).scalar_one()

    def list_for_user(self, user_id: UUID) -> list[EducationRecord]:
        return list(self.session.scalars(select(EducationRecord).where(EducationRecord.user_id == user_id)
                    .order_by(EducationRecord.created_at, EducationRecord.id)))

    def get_owned(self, education_id: UUID, user_id: UUID) -> EducationRecord | None:
        return self.session.scalar(select(EducationRecord).where(
            EducationRecord.id == education_id, EducationRecord.user_id == user_id))

    def clear_primary_for_user(self, user_id: UUID) -> None:
        # Executes before the new primary is assigned; avoids transient unique conflicts.
        self.session.execute(update(EducationRecord).where(
            EducationRecord.user_id == user_id, EducationRecord.is_primary.is_(True)
        ).values(is_primary=False))

    def add(self, record: EducationRecord) -> None:
        self.session.add(record)

    def delete(self, record: EducationRecord) -> None:
        self.session.delete(record)
