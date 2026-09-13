"""Atomic artifact metadata changes; no profile synchronization."""

from backend.app.models.artifact import CareerArtifact
from backend.app.repositories.artifact import ArtifactRepository
from backend.app.schemas.artifact import ArtifactCreate, ArtifactRead


class ArtifactService:
    @staticmethod
    def list(owner, uow):
        return [
            ArtifactRead.model_validate(row) for row in ArtifactRepository(uow.session).list(owner)
        ]

    @staticmethod
    def get(owner, id, uow):
        return ArtifactRead.model_validate(ArtifactRepository(uow.session).owned(owner, id))

    @staticmethod
    def save(owner, payload, uow, id=None):
        row = ArtifactRepository(uow.session).owned(owner, id, lock=True) if id else None
        changes = payload.model_dump(exclude_unset=True)
        existing = {key: getattr(row, key) for key in ArtifactCreate.model_fields} if row else {}
        final = ArtifactCreate.model_validate({**existing, **changes})
        if row is None:
            row = CareerArtifact(user_id=owner, **final.model_dump())
            uow.session.add(row)
        else:
            for key, value in final.model_dump().items():
                if getattr(row, key) != value:
                    setattr(row, key, value)
        uow.session.flush()
        result = ArtifactRead.model_validate(row)
        uow.commit()
        return result

    @staticmethod
    def delete(owner, id, uow):
        uow.session.delete(ArtifactRepository(uow.session).owned(owner, id, lock=True))
        uow.commit()
