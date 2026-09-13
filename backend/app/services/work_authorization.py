"""Owned facts, stable row edits, server confirmation and narrow conflict handling."""
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.models.base import utc_now
from backend.app.models.profile import WorkAuthorization
from backend.app.repositories.work_authorization import WorkAuthorizationRepository
from backend.app.schemas.work_authorization import (
    WorkAuthorizationCreate,
    WorkAuthorizationRead,
    WorkAuthorizationUpdate,
)


def owned_or_not_found(repository, record_id, user_id):
    record = repository.get_owned_for_update(record_id, user_id)
    if record is None:
        raise StudentSuccessfulException(404, "WORK_AUTHORIZATION_NOT_FOUND", "Work authorization record not found")
    return record


def commit_facts(uow):
    try:
        uow.commit()
    except IntegrityError as error:
        uow.rollback()
        if getattr(error.orig, "pgcode", None) == "23505" and getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "uq_work_auth_user_country":
            raise StudentSuccessfulException(409, "WORK_AUTHORIZATION_ALREADY_EXISTS", "A work authorization record already exists for this country") from error
        raise


class WorkAuthorizationService:
    @staticmethod
    def list_for_user(user_id: UUID, uow: UnitOfWork) -> list[WorkAuthorizationRead]:
        return [WorkAuthorizationRead.model_validate(row) for row in WorkAuthorizationRepository(uow.session).list_for_user(user_id)]

    @staticmethod
    def create(user_id: UUID, payload: WorkAuthorizationCreate, uow: UnitOfWork) -> WorkAuthorizationRead:
        record = WorkAuthorization(user_id=user_id, **payload.model_dump(), last_confirmed_at=utc_now())
        WorkAuthorizationRepository(uow.session).add(record)
        commit_facts(uow)
        return WorkAuthorizationRead.model_validate(record)

    @staticmethod
    def update(user_id: UUID, record_id: UUID, payload: WorkAuthorizationUpdate, uow: UnitOfWork) -> WorkAuthorizationRead:
        record = owned_or_not_found(WorkAuthorizationRepository(uow.session), record_id, user_id)
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return WorkAuthorizationRead.model_validate(record)
        existing = {field: getattr(record, field) for field in WorkAuthorizationCreate.model_fields}
        final = WorkAuthorizationCreate.model_validate({**existing, **changes})
        for field in changes:
            setattr(record, field, getattr(final, field))
        record.last_confirmed_at = utc_now()
        commit_facts(uow)
        return WorkAuthorizationRead.model_validate(record)

    @staticmethod
    def delete(user_id: UUID, record_id: UUID, uow: UnitOfWork) -> None:
        repository = WorkAuthorizationRepository(uow.session)
        repository.delete(owned_or_not_found(repository, record_id, user_id))
        uow.commit()
