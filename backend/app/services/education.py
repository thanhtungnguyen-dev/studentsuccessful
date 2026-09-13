"""Education final-state validation and one-commit, per-owner mutations."""

from uuid import UUID

from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.models.profile import EducationRecord
from backend.app.repositories.education import EducationRepository
from backend.app.schemas.education import EducationCreate, EducationRead, EducationUpdate


def owned_or_not_found(repository: EducationRepository, education_id: UUID, user_id: UUID):
    record = repository.get_owned(education_id, user_id)
    if record is None:
        raise StudentSuccessfulException(404, "EDUCATION_NOT_FOUND", "Education record not found")
    return record


class EducationService:
    @staticmethod
    def list_for_user(user_id: UUID, uow: UnitOfWork) -> list[EducationRead]:
        assert uow.session is not None
        return [EducationRead.model_validate(record) for record in EducationRepository(uow.session).list_for_user(user_id)]

    @staticmethod
    def create(user_id: UUID, payload: EducationCreate, uow: UnitOfWork) -> EducationRead:
        assert uow.session is not None
        repository = EducationRepository(uow.session)
        repository.lock_owner(user_id)
        if payload.is_primary:
            repository.clear_primary_for_user(user_id)
        record = EducationRecord(user_id=user_id, **payload.model_dump())
        repository.add(record)
        uow.commit()
        return EducationRead.model_validate(record)

    @staticmethod
    def update(user_id: UUID, education_id: UUID, payload: EducationUpdate, uow: UnitOfWork) -> EducationRead:
        assert uow.session is not None
        repository = EducationRepository(uow.session)
        repository.lock_owner(user_id)
        record = owned_or_not_found(repository, education_id, user_id)
        changes = payload.model_dump(exclude_unset=True)
        existing = {field: getattr(record, field) for field in EducationCreate.model_fields}
        final = EducationCreate.model_validate({**existing, **changes})
        # Validate before any demotion or assignment, including a mixed GPA/primary edit.
        if changes.get("is_primary") is True:
            repository.clear_primary_for_user(user_id)
        for field in changes:
            setattr(record, field, getattr(final, field))
        uow.commit()
        return EducationRead.model_validate(record)

    @staticmethod
    def delete(user_id: UUID, education_id: UUID, uow: UnitOfWork) -> None:
        assert uow.session is not None
        repository = EducationRepository(uow.session)
        repository.lock_owner(user_id)
        repository.delete(owned_or_not_found(repository, education_id, user_id))
        uow.commit()
