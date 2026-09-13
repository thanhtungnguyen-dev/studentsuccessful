"""Domain and application exceptions mapping to standard RFC 7807 error codes."""

from fastapi import HTTPException, status


class StudentSuccessfulException(HTTPException):
    def __init__(self, status_code: int, code: str, detail: str):
        super().__init__(
            status_code=status_code,
            detail={"code": code, "detail": detail},
        )
        self.code = code
        self.error_detail = detail


class InvalidCredentialsException(StudentSuccessfulException):
    def __init__(self, detail: str = "Invalid email or password"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_CREDENTIALS",
            detail=detail,
        )


class NotAuthenticatedException(StudentSuccessfulException):
    def __init__(self, detail: str = "Authentication required"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHENTICATED",
            detail=detail,
        )


class SessionExpiredException(StudentSuccessfulException):
    def __init__(self, detail: str = "Session has expired"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="SESSION_EXPIRED",
            detail=detail,
        )


class SessionRevokedException(StudentSuccessfulException):
    def __init__(self, detail: str = "Session has been revoked"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="SESSION_REVOKED",
            detail=detail,
        )


class EmailAlreadyExistsException(StudentSuccessfulException):
    def __init__(self, detail: str = "Email is already registered"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code="EMAIL_ALREADY_REGISTERED",
            detail=detail,
        )


class CsrfTokenInvalidException(StudentSuccessfulException):
    def __init__(self, detail: str = "Invalid or missing CSRF token"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code="CSRF_TOKEN_INVALID",
            detail=detail,
        )


class AuthOriginRejectedException(StudentSuccessfulException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code="AUTH_ORIGIN_REJECTED",
            detail="A trusted frontend Origin is required",
        )


__all__ = [
    "AuthOriginRejectedException",
    "StudentSuccessfulException",
    "InvalidCredentialsException",
    "NotAuthenticatedException",
    "SessionExpiredException",
    "SessionRevokedException",
    "EmailAlreadyExistsException",
    "CsrfTokenInvalidException",
]
