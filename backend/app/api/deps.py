"""Authentication, host-only cookies, and mutation protection dependencies."""

from collections.abc import Generator

from fastapi import Depends, Header, Request, Response

from backend.app.core.config import settings
from backend.app.core.exceptions import AuthOriginRejectedException, CsrfTokenInvalidException
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.models.user import User, UserSession
from backend.app.services.auth import AuthService

CSRF_COOKIE_NAME = "ss_csrf"


def get_uow() -> Generator[UnitOfWork, None, None]:
    with UnitOfWork() as uow:
        yield uow


def session_cookie_name() -> str:
    """Use the practical HTTP fallback only when secure cookies are disabled."""
    if not settings.SESSION_COOKIE_SECURE and settings.SESSION_COOKIE_NAME.startswith("__Host-"):
        return "ss_session"
    return settings.SESSION_COOKIE_NAME


def get_session_token_from_request(request: Request) -> str | None:
    # Production must never authenticate using a weaker development cookie name.
    return request.cookies.get(session_cookie_name())


def set_auth_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    for name, token, http_only in (
        (session_cookie_name(), session_token, True),
        (CSRF_COOKIE_NAME, csrf_token, False),
    ):
        response.set_cookie(
            key=name,
            value=token,
            httponly=http_only,
            secure=settings.SESSION_COOKIE_SECURE,
            samesite="lax",
            path="/",
            max_age=settings.SESSION_EXPIRE_DAYS * 86400,
        )


def clear_auth_cookies(response: Response) -> None:
    for name, http_only in ((session_cookie_name(), True), (CSRF_COOKIE_NAME, False)):
        response.delete_cookie(
            key=name,
            path="/",
            httponly=http_only,
            secure=settings.SESSION_COOKIE_SECURE,
            samesite="lax",
        )


def require_auth_origin(
    request: Request,
    origin: str | None = Header(
        None,
        alias="Origin",
        description="Must match FRONTEND_ORIGIN; required in production (403 if rejected).",
    ),
) -> None:
    """Protect login/register before a session-bound CSRF token exists.

    Compare the browser-facing origin, including its port, never Host or forwarded
    headers. A Next.js same-origin rewrite must preserve the browser Origin.
    Missing Origin is permitted only for non-production CLI/test clients.
    """
    origins = request.headers.getlist("origin")
    if not origins and settings.APP_ENV != "production":
        return
    if len(origins) != 1 or origin != settings.FRONTEND_ORIGIN:
        raise AuthOriginRejectedException()


def get_current_user_and_session(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
) -> tuple[User, UserSession]:
    return AuthService.get_current_user_and_session(get_session_token_from_request(request), uow)


def get_current_user(
    user_and_session: tuple[User, UserSession] = Depends(get_current_user_and_session),
) -> User:
    return user_and_session[0]


def require_csrf(
    x_csrf_token: str | None = Header(
        None,
        alias="X-CSRF-Token",
        description="Session's stable CSRF token; missing or invalid values return 403.",
    ),
    user_and_session: tuple[User, UserSession] = Depends(get_current_user_and_session),
) -> tuple[User, UserSession]:
    """Validate the header against this authenticated session's stored digest."""
    _, session = user_and_session
    if not AuthService.verify_csrf_token(session, x_csrf_token):
        raise CsrfTokenInvalidException()
    return user_and_session
