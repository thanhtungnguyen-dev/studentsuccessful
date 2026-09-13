"""Main FastAPI application entry point."""

import logging
import re
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.alert import router as alert_router
from backend.app.api.application import router as application_router
from backend.app.api.artifact import router as artifact_router
from backend.app.api.auth import router as auth_router
from backend.app.api.candidate_profile import router as candidate_profile_router
from backend.app.api.education import router as education_router
from backend.app.api.employment import router as employment_router
from backend.app.api.health import router as health_router
from backend.app.api.job import router as job_router
from backend.app.api.portfolio import router as portfolio_router
from backend.app.api.preferences import router as preferences_router
from backend.app.api.profile import router as profile_router
from backend.app.api.resume import router as resume_router
from backend.app.api.saved_search import router as saved_search_router
from backend.app.api.work_authorization import router as work_authorization_router
from backend.app.core.config import settings
from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.core.logging import (
    configure_logging,
    current_request_id,
    reset_request_id,
    set_request_id,
)

configure_logging()
logger = logging.getLogger("studentsuccessful.api")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

app = FastAPI(
    title=settings.APP_NAME,
    description="Maintainable Career & Internship Platform for Students API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    debug=settings.DEBUG,
)


@app.exception_handler(StudentSuccessfulException)
async def domain_exception_handler(request: Request, exc: StudentSuccessfulException):
    logger.warning(
        "domain_request_rejected",
        extra={
            "event": "domain_request_rejected",
            "request_id": current_request_id(),
            "method": request.method,
            "path": request.url.path,
            "status_code": exc.status_code,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": "about:blank",
            "title": exc.code,
            "status": exc.status_code,
            "detail": exc.error_detail,
            "code": exc.code,
            "instance": str(request.url.path),
        },
    )


@app.middleware("http")
async def request_observability_and_security(request: Request, call_next):
    """Attach a safe request correlation ID and production-safe response headers."""

    supplied = request.headers.getlist("x-request-id")
    request_id = supplied[0] if len(supplied) == 1 and _REQUEST_ID.fullmatch(supplied[0]) else uuid4().hex
    context = set_request_id(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "http_request_failed",
            extra={
                "event": "http_request_failed",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round((time.perf_counter() - started) * 1000),
            },
        )
        raise
    finally:
        reset_request_id(context)

    response.headers["X-Request-ID"] = request_id
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
    if request.url.path != "/docs":
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
    if settings.APP_ENV == "production":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    logger.info(
        "http_request_completed",
        extra={
            "event": "http_request_completed",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000),
        },
    )
    return response


@app.middleware("http")
async def no_store_auth_responses(request: Request, call_next):
    """Scope cache protection to personal API responses, including errors."""
    response = await call_next(request)
    if request.url.path.startswith(
        (
            "/api/v1/auth/",
            "/api/v1/jobs",
            "/api/v1/saved-searches",
            "/api/v1/alerts",
            "/api/v1/applications",
            "/api/v1/resumes",
            "/api/v1/resume-versions/",
            "/api/v1/profile/candidate",
        )
    ):
        response.headers["Cache-Control"] = "no-store"
    return response


# Exact browser-facing origin; no implicit development origins in production.
origins = [settings.FRONTEND_ORIGIN]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)

# Mount Routers
app.include_router(health_router)
app.include_router(job_router, prefix="/api/v1")
app.include_router(saved_search_router, prefix="/api/v1")
app.include_router(alert_router, prefix="/api/v1")
app.include_router(application_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(profile_router, prefix="/api/v1")

app.include_router(candidate_profile_router, prefix="/api/v1")

app.include_router(education_router, prefix="/api/v1")

app.include_router(employment_router, prefix="/api/v1")

app.include_router(work_authorization_router, prefix="/api/v1")

app.include_router(preferences_router, prefix="/api/v1")

app.include_router(portfolio_router, prefix="/api/v1")

app.include_router(artifact_router, prefix="/api/v1")

app.include_router(resume_router, prefix="/api/v1")
