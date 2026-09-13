"""Authentication domain service implementing registration, login, session management, and CSRF."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError

from backend.app.core.config import settings
from backend.app.core.exceptions import (
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    NotAuthenticatedException,
    SessionExpiredException,
    SessionRevokedException,
)
from backend.app.core.security import (
    generate_secure_token,
    hash_password,
    hash_token,
    normalize_email,
    verify_password,
    verify_token,
)
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.models.user import User, UserSession


class AuthService:
    """Authentication and session lifecycle management."""

    @staticmethod
    def register(email: str, password: str, uow: UnitOfWork) -> tuple[User, str, str]:
        """
        Registers a new user, creates an active session, and returns (user, raw_session_token, raw_csrf_token).
        """
        assert uow.session is not None, "UnitOfWork session must be active"
        clean_email = normalize_email(email)

        # Ensure no existing account with same normalized email
        existing = uow.session.query(User).filter(func.lower(User.email) == clean_email).first()
        if existing:
            raise EmailAlreadyExistsException()

        # Hash password with Argon2id
        hashed_pw = hash_password(password)

        user = User(
            email=clean_email,
            password_hash=hashed_pw,
            is_active=True,
        )
        uow.session.add(user)
        try:
            uow.session.flush()  # populate user.id and enforce email uniqueness
        except IntegrityError as exc:
            # The pre-check is only a convenience: a concurrent request can win.
            # Translate only this known constraint; do not hide unrelated failures.
            uow.rollback()
            if (
                getattr(exc.orig, "pgcode", None) == "23505"
                and getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
                == "idx_users_email_lower"
            ):
                raise EmailAlreadyExistsException() from exc
            raise

        # Generate random 256-bit credentials
        raw_session_token = generate_secure_token(32)
        raw_csrf_token = generate_secure_token(32)

        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.SESSION_EXPIRE_DAYS)

        session = UserSession(
            user_id=user.id,
            session_token_hash=hash_token(raw_session_token),
            csrf_token_hash=hash_token(raw_csrf_token),
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
        )
        uow.session.add(session)
        uow.commit()

        return user, raw_session_token, raw_csrf_token

    @staticmethod
    def login(email: str, password: str, uow: UnitOfWork) -> tuple[User, str, str]:
        """
        Authenticates user credentials. Returns (user, raw_session_token, raw_csrf_token).
        Never reveals whether email exists if authentication fails.
        """
        assert uow.session is not None, "UnitOfWork session must be active"
        clean_email = normalize_email(email)

        user = uow.session.query(User).filter(func.lower(User.email) == clean_email).first()
        if not user or not user.is_active:
            raise InvalidCredentialsException()

        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsException()

        # Generate random 256-bit credentials
        raw_session_token = generate_secure_token(32)
        raw_csrf_token = generate_secure_token(32)

        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.SESSION_EXPIRE_DAYS)

        session = UserSession(
            user_id=user.id,
            session_token_hash=hash_token(raw_session_token),
            csrf_token_hash=hash_token(raw_csrf_token),
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
        )
        uow.session.add(session)
        uow.commit()

        return user, raw_session_token, raw_csrf_token

    @staticmethod
    def complete_onboarding(user: User, uow: UnitOfWork) -> User:
        """Conditional update serializes competing writers; the first timestamp wins."""
        assert uow.session is not None, "UnitOfWork session must be active"
        uow.session.execute(
            update(User)
            .where(User.id == user.id, User.onboarding_completed_at.is_(None))
            .values(onboarding_completed_at=func.clock_timestamp(), updated_at=User.updated_at)
            .execution_options(synchronize_session=False)
        )
        uow.commit()
        # Authentication may have loaded NULL before another request committed.
        uow.session.refresh(user)
        return user

    @staticmethod
    def logout(session: UserSession, uow: UnitOfWork) -> None:
        """Revoke the session already authenticated and CSRF-validated by the route."""
        assert uow.session is not None, "UnitOfWork session must be active"
        session.revoked_at = datetime.now(timezone.utc)
        uow.commit()

    @staticmethod
    def get_current_user_and_session(
        raw_session_token: str | None, uow: UnitOfWork
    ) -> tuple[User, UserSession]:
        """
        Validates the raw session token.
        Raises NotAuthenticatedException, SessionRevokedException, or SessionExpiredException if invalid.
        """
        if not raw_session_token:
            raise NotAuthenticatedException()

        assert uow.session is not None, "UnitOfWork session must be active"
        token_hash = hash_token(raw_session_token)

        session = (
            uow.session.query(UserSession)
            .filter(UserSession.session_token_hash == token_hash)
            .first()
        )
        if not session:
            raise NotAuthenticatedException()

        if session.revoked_at is not None:
            raise SessionRevokedException()

        if session.expires_at <= datetime.now(timezone.utc):
            raise SessionExpiredException()

        user = uow.session.query(User).filter(User.id == session.user_id).first()
        if not user or not user.is_active:
            raise NotAuthenticatedException()

        # Absolute expiry and activity timestamps are never extended by reads.
        return user, session

    @staticmethod
    def verify_csrf_token(session: UserSession, raw_csrf_token: str | None) -> bool:
        """Verifies candidate CSRF token against session hash in constant time."""
        if not raw_csrf_token:
            return False
        return verify_token(raw_csrf_token, session.csrf_token_hash)


__all__ = ["AuthService"]
