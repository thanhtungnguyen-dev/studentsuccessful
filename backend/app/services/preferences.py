"""Atomic per-user replacement, with validation before destructive writes."""
from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.repositories.preferences import (
    SELECTIONS,
    CatalogRepository,
    PreferencesRepository,
)
from backend.app.schemas.preferences import CatalogItem, CatalogLocation


class PreferencesService:
    @staticmethod
    def get(user_id, uow):
        repository = PreferencesRepository(uow.session)
        # A shared aggregate lock prevents torn reads across its multiple tables.
        repository.lock_owner(user_id, read=True)
        return repository.read(user_id)

    @staticmethod
    def replace(user_id, values, uow):
        repository = PreferencesRepository(uow.session)
        repository.lock_owner(user_id)
        for field in SELECTIONS:
            if not repository.valid_ids(field, getattr(values, field)):
                raise StudentSuccessfulException(422, "INVALID_PREFERENCE_SELECTION", f"Unknown catalog ID in {field}")
        if not repository.exists(user_id) or repository.read(user_id) != values:
            repository.replace(user_id, values)
        uow.commit()
        return values


class CatalogService:
    @staticmethod
    def list(model, uow, location=False, **filters):
        schema = CatalogLocation if location else CatalogItem
        return [schema.model_validate(row) for row in CatalogRepository(uow.session).list(model, **filters)]
