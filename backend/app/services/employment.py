"""Employment final-state validation and one-commit, row-scoped mutations."""

from uuid import UUID

from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.models.profile import EmploymentRecord
from backend.app.repositories.employment import EmploymentRepository
from backend.app.schemas.employment import EmploymentCreate, EmploymentRead, EmploymentUpdate


def owned_or_not_found(repository: EmploymentRepository, employment_id: UUID, user_id: UUID):
    record = repository.get_owned_for_update(employment_id, user_id)
    if record is None:
        raise StudentSuccessfulException(404, "EMPLOYMENT_NOT_FOUND", "Employment record not found")
    return record


class EmploymentService:
    @staticmethod
    def list_for_user(user_id: UUID, uow: UnitOfWork) -> list[EmploymentRead]:
        assert uow.session is not None
        return [EmploymentRead.model_validate(record) for record in EmploymentRepository(uow.session).list_for_user(user_id)]

    @staticmethod
    def create(user_id: UUID, payload: EmploymentCreate, uow: UnitOfWork) -> EmploymentRead:
        assert uow.session is not None
        repository = EmploymentRepository(uow.session)
        record = EmploymentRecord(user_id=user_id, **payload.model_dump())
        repository.add(record)
        uow.commit()
        return EmploymentRead.model_validate(record)

    @staticmethod
    def update(user_id: UUID, employment_id: UUID, payload: EmploymentUpdate, uow: UnitOfWork) -> EmploymentRead:
        assert uow.session is not None
        repository = EmploymentRepository(uow.session)
        record = owned_or_not_found(repository, employment_id, user_id)
        changes = payload.model_dump(exclude_unset=True)
        existing = {field: getattr(record, field) for field in EmploymentCreate.model_fields}
        final = EmploymentCreate.model_validate({**existing, **changes})
        # Validate the locked row plus supplied changes before assigning any facts.
        for field in changes:
            setattr(record, field, getattr(final, field))
        uow.commit()
        return EmploymentRead.model_validate(record)

    @staticmethod
    def delete(user_id: UUID, employment_id: UUID, uow: UnitOfWork) -> None:
        assert uow.session is not None
        repository = EmploymentRepository(uow.session)
        repository.delete(owned_or_not_found(repository, employment_id, user_id))
        uow.commit()
