"""Application Facts only; transaction boundaries belong to this service."""

from uuid import UUID

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.models.profile import ApplicationProfile
from backend.app.repositories.profile import ApplicationProfileRepository
from backend.app.schemas.profile import ProfileRead, ProfileUpdate


class ApplicationProfileService:
    @staticmethod
    def read(user_id: UUID, uow: UnitOfWork) -> ProfileRead | None:
        assert uow.session is not None
        profile = ApplicationProfileRepository(uow.session).get_for_user(user_id)
        return ProfileRead.model_validate(profile) if profile is not None else None

    @staticmethod
    def update(user_id: UUID, payload: ProfileUpdate, uow: UnitOfWork) -> ProfileRead:
        assert uow.session is not None
        repository = ApplicationProfileRepository(uow.session)
        repository.lock_owner(user_id)
        profile = repository.get_for_user(user_id)
        changes = payload.model_dump(exclude_unset=True)
        if profile is None:
            # Missing required legal names raises Pydantic validation, before any insert.
            values = ProfileRead.model_validate(changes)
            profile = ApplicationProfile(user_id=user_id, **values.model_dump())
            repository.add(profile)
        elif changes:
            for field, value in changes.items():
                setattr(profile, field, value)
        else:
            return ProfileRead.model_validate(profile)
        uow.commit()
        return ProfileRead.model_validate(profile)
