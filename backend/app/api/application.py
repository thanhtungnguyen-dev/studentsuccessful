"""Private manual application tracking routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError

from backend.app.api.deps import get_current_user, get_uow, require_csrf
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.models.user import User
from backend.app.schemas.application import (
    ApplicationCreate,
    ApplicationFilterStatus,
    ApplicationListRead,
    ApplicationRead,
    ApplicationUpdate,
)
from backend.app.schemas.common import ProblemDetail
from backend.app.services.application import ApplicationService


def reject_application_query(request: Request) -> None:
    if "id" in request.path_params and request.query_params:
        raise RequestValidationError(
            [
                {
                    "type": "extra_forbidden",
                    "loc": ("query", name),
                    "msg": "Extra inputs are not permitted",
                }
                for name in sorted(request.query_params)
            ]
        )
    unexpected = sorted(set(request.query_params) - {"status"})
    if unexpected:
        raise RequestValidationError(
            [
                {
                    "type": "extra_forbidden",
                    "loc": ("query", name),
                    "msg": "Extra inputs are not permitted",
                }
                for name in unexpected
            ]
        )


router = APIRouter(
    prefix="/applications",
    tags=["applications"],
    dependencies=[Depends(reject_application_query)],
    responses={
        401: {"model": ProblemDetail},
        403: {"model": ProblemDetail},
        404: {"model": ProblemDetail},
        409: {"model": ProblemDetail},
        422: {"model": ProblemDetail},
    },
)


@router.get("", response_model=ApplicationListRead)
def list_applications(
    response: Response,
    status: ApplicationFilterStatus = Query("ALL"),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
):
    response.headers["Cache-Control"] = "no-store"
    return ApplicationService.list(user.id, status, uow)


@router.post("", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def create_application(
    payload: ApplicationCreate,
    response: Response,
    authenticated=Depends(require_csrf),
    uow: UnitOfWork = Depends(get_uow),
):
    response.headers["Cache-Control"] = "no-store"
    return ApplicationService.create(authenticated[0].id, payload, uow)


@router.get("/{id}", response_model=ApplicationRead)
def get_application(
    id: UUID,
    response: Response,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
):
    response.headers["Cache-Control"] = "no-store"
    return ApplicationService.get(user.id, id, uow)


@router.patch("/{id}", response_model=ApplicationRead)
def update_application(
    id: UUID,
    payload: ApplicationUpdate,
    response: Response,
    authenticated=Depends(require_csrf),
    uow: UnitOfWork = Depends(get_uow),
):
    response.headers["Cache-Control"] = "no-store"
    return ApplicationService.update(authenticated[0].id, id, payload, uow)
