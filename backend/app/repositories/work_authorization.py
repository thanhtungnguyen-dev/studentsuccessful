"""Owner-scoped work_authorization rows; no user aggregate lock or repository commits."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.profile import WorkAuthorization


class WorkAuthorizationRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_for_user(self, user_id: UUID) -> list[WorkAuthorization]:
        return list(self.session.scalars(select(WorkAuthorization).where(WorkAuthorization.user_id == user_id)
                    .order_by(WorkAuthorization.country_code, WorkAuthorization.id)))

    def get_owned_for_update(self, work_authorization_id: UUID, user_id: UUID) -> WorkAuthorization | None:
        return self.session.scalar(select(WorkAuthorization).where(
            WorkAuthorization.id == work_authorization_id, WorkAuthorization.user_id == user_id
        ).with_for_update().execution_options(populate_existing=True))

    def add(self, record: WorkAuthorization) -> None:
        self.session.add(record)

    def delete(self, record: WorkAuthorization) -> None:
        self.session.delete(record)
