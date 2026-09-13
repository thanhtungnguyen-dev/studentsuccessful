"""Owner-scoped employment rows; no user aggregate lock or repository commits."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.profile import EmploymentRecord


class EmploymentRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_for_user(self, user_id: UUID) -> list[EmploymentRecord]:
        return list(self.session.scalars(select(EmploymentRecord).where(EmploymentRecord.user_id == user_id)
                    .order_by(EmploymentRecord.created_at, EmploymentRecord.id)))

    def get_owned_for_update(self, employment_id: UUID, user_id: UUID) -> EmploymentRecord | None:
        return self.session.scalar(select(EmploymentRecord).where(
            EmploymentRecord.id == employment_id, EmploymentRecord.user_id == user_id
        ).with_for_update().execution_options(populate_existing=True))

    def add(self, record: EmploymentRecord) -> None:
        self.session.add(record)

    def delete(self, record: EmploymentRecord) -> None:
        self.session.delete(record)
