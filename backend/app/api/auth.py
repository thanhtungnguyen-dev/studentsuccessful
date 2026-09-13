"""Authentication endpoints with stable per-session CSRF cookies."""

from fastapi import APIRouter, Depends, Response, status

from backend.app.api.deps import (
    clear_auth_cookies,
    get_current_user,
    get_uow,
    require_auth_origin,
    require_csrf,
    set_auth_cookies,
)
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.models.user import User
from backend.app.schemas.auth import (
    AuthResponse,
    CompleteOnboardingRequest,
    LoginRequest,
    LogoutResponse,
    RegisterRequest,
    UserResponse,
)
from backend.app.schemas.common import ProblemDetail
from backend.app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_auth_origin)],
    responses={403: {"model": ProblemDetail}, 409: {"model": ProblemDetail}},
    summary="Register a user and set session and stable CSRF cookies",
)
def register(
    payload: RegisterRequest,
    response: Response,
    uow: UnitOfWork = Depends(get_uow),
) -> AuthResponse:
    user, raw_session_token, raw_csrf_token = AuthService.register(
        email=payload.email,
        password=payload.password,
        uow=uow,
    )
    set_auth_cookies(response, raw_session_token, raw_csrf_token)
    return AuthResponse(user=UserResponse.model_validate(user), csrf_token=raw_csrf_token)


@router.post(
    "/login",
    response_model=AuthResponse,
    dependencies=[Depends(require_auth_origin)],
    responses={401: {"model": ProblemDetail}, 403: {"model": ProblemDetail}},
    summary="Authenticate and set a new session and stable CSRF cookie pair",
)
def login(
    payload: LoginRequest,
    response: Response,
    uow: UnitOfWork = Depends(get_uow),
) -> AuthResponse:
    user, raw_session_token, raw_csrf_token = AuthService.login(
        email=payload.email,
        password=payload.password,
        uow=uow,
    )
    set_auth_cookies(response, raw_session_token, raw_csrf_token)
    return AuthResponse(user=UserResponse.model_validate(user), csrf_token=raw_csrf_token)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    responses={401: {"model": ProblemDetail}, 403: {"model": ProblemDetail}},
    summary="Authenticate, validate CSRF, revoke current session and clear both cookies",
)
def logout(
    response: Response,
    authenticated=Depends(require_csrf),
    uow: UnitOfWork = Depends(get_uow),
) -> LogoutResponse:
    _, session = authenticated
    AuthService.logout(session, uow)
    clear_auth_cookies(response)
    return LogoutResponse(message="Successfully logged out")


@router.get(
    "/me",
    response_model=UserResponse,
    responses={401: {"model": ProblemDetail}},
    summary="Read current user without changing session state or absolute expiry",
)
def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post(
    "/onboarding/complete",
    response_model=UserResponse,
    responses={401: {"model": ProblemDetail}, 403: {"model": ProblemDetail}},
    summary="Persist the current user's first explicit onboarding completion",
)
def complete_onboarding(
    payload: CompleteOnboardingRequest,
    authenticated=Depends(require_csrf),
    uow: UnitOfWork = Depends(get_uow),
) -> UserResponse:
    user, _ = authenticated
    return UserResponse.model_validate(AuthService.complete_onboarding(user, uow))


__all__ = ["router"]
