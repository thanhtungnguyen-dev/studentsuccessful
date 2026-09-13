"""Atomic user-owned factual Skills and Projects."""

from backend.app.models.base import utc_now
from backend.app.models.portfolio import Project
from backend.app.repositories.portfolio import PortfolioRepository
from backend.app.schemas.portfolio import ProjectCreate


class PortfolioService:
    @staticmethod
    def skills(owner, uow, values=None):
        repository = PortfolioRepository(uow.session)
        repository.lock_owner(owner, read=values is None)
        if values is None:
            return repository.skills(owner)
        repository.validate(values)
        repository.replace_skills(owner, values)
        uow.commit()
        return values

    @staticmethod
    def list_projects(owner, uow, id=None):
        repository = PortfolioRepository(uow.session)
        repository.lock_owner(owner, read=True)
        return (
            repository.projects(owner)
            if id is None
            else repository.project_read(repository.project(owner, id))
        )

    @staticmethod
    def save_project(owner, payload, uow, id=None):
        repository = PortfolioRepository(uow.session)
        repository.lock_owner(owner)
        row = repository.project(owner, id) if id else None
        existing = repository.project_read(row) if row else None
        changes = payload.model_dump(exclude_unset=True)
        values = ProjectCreate.model_validate(
            {
                **(
                    existing.model_dump(exclude={"id", "created_at", "updated_at"})
                    if existing
                    else {}
                ),
                **changes,
            }
        )
        repository.validate(values.technologies)
        if row is None:
            row = Project(user_id=owner, **values.model_dump(exclude={"technologies"}))
            uow.session.add(row)
            uow.session.flush()
        elif values.model_dump() != existing.model_dump(exclude={"id", "created_at", "updated_at"}):
            for key, value in values.model_dump(exclude={"technologies"}).items():
                setattr(row, key, value)
            row.updated_at = utc_now()
        repository.replace_technologies(row.id, values.technologies)
        uow.session.flush()
        result = repository.project_read(row)
        uow.commit()
        return result

    @staticmethod
    def delete_project(owner, id, uow):
        repository = PortfolioRepository(uow.session)
        repository.lock_owner(owner)
        uow.session.delete(repository.project(owner, id))
        uow.commit()
