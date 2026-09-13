"""Unit of work and base repository abstraction for transaction lifecycle."""

from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.core.database import SessionLocal

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Generic repository handling basic persistence operations on SQLAlchemy models."""

    def __init__(self, session: Session, model_class: type[T]):
        self.session = session
        self.model_class = model_class

    def get_by_id(self, id_val: UUID) -> T | None:
        return self.session.query(self.model_class).filter_by(id=id_val).first()

    def get_all(self, skip: int = 0, limit: int = 100) -> list[T]:
        return self.session.query(self.model_class).offset(skip).limit(limit).all()

    def add(self, entity: T) -> T:
        self.session.add(entity)
        return entity

    def delete(self, entity: T) -> None:
        self.session.delete(entity)


class UnitOfWork:
    """
    Manages explicit transactional boundaries across repositories.
    Requires an explicit call to `commit()` before exiting the context manager.
    If an exception occurs OR if `commit()` was not explicitly called, all uncommitted
    changes are rolled back cleanly.
    """

    def __init__(self, session_factory=None):
        self.session_factory = session_factory or SessionLocal
        self.session: Session | None = None
        self._committed: bool = False

    def __enter__(self):
        self.session = self.session_factory()
        self._committed = False
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session is not None:
            if exc_type is not None or not self._committed:
                self.rollback()
            self.session.close()

    def commit(self) -> None:
        """Explicitly commits the current transaction."""
        if self.session is not None:
            self.session.commit()
            self._committed = True

    def rollback(self) -> None:
        """Rolls back the current transaction."""
        if self.session is not None:
            self.session.rollback()
