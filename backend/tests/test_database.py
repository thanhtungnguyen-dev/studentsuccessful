"""Tests for database connectivity, transactions, and explicit unit of work semantics."""

from backend.app.core.unit_of_work import BaseRepository, UnitOfWork
from backend.app.models.base import generate_uuid
from backend.app.models.user import User


def test_unit_of_work_explicit_commit():
    """Verify that UnitOfWork persists data ONLY when commit() is explicitly called."""
    test_email = f"student_{str(generate_uuid())[:8]}@university.edu"

    with UnitOfWork() as uow:
        repo = BaseRepository(uow.session, User)
        new_user = User(
            email=test_email,
            password_hash="argon2_hashed_secret",
            is_active=True,
        )
        repo.add(new_user)
        uow.commit()
        user_id = new_user.id

    # Verify state exists in a separate session
    with UnitOfWork() as uow:
        repo = BaseRepository(uow.session, User)
        queried = repo.get_by_id(user_id)
        assert queried is not None
        assert queried.email == test_email

        # Clean up
        repo.delete(queried)
        uow.commit()


def test_unit_of_work_rollback_on_no_commit():
    """Verify that exiting context without calling commit() safely rolls back changes (read-only protection)."""
    test_email = f"uncommitted_{str(generate_uuid())[:8]}@university.edu"

    with UnitOfWork() as uow:
        repo = BaseRepository(uow.session, User)
        uncommitted_user = User(
            email=test_email,
            password_hash="argon2_hashed_secret",
            is_active=True,
        )
        repo.add(uncommitted_user)
        uow.session.flush()
        # Deliberately NOT calling uow.commit()

    # Verify that nothing was persisted to the database
    with UnitOfWork() as uow:
        queried = uow.session.query(User).filter_by(email=test_email).first()
        assert queried is None


def test_unit_of_work_rollback_on_exception():
    """Verify that raising an exception inside context manager triggers automatic rollback."""
    test_email = f"errored_{str(generate_uuid())[:8]}@university.edu"

    try:
        with UnitOfWork() as uow:
            repo = BaseRepository(uow.session, User)
            user = User(
                email=test_email,
                password_hash="argon2_hashed_secret",
                is_active=True,
            )
            repo.add(user)
            uow.session.flush()
            raise RuntimeError("Simulated service failure")
    except RuntimeError:
        pass

    # Verify that nothing was persisted
    with UnitOfWork() as uow:
        queried = uow.session.query(User).filter_by(email=test_email).first()
        assert queried is None
