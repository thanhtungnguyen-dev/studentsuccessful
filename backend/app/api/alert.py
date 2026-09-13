"""Private in-app new-job alert inbox routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError

from backend.app.api.deps import get_current_user, get_uow, require_csrf
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.models.user import User
from backend.app.schemas.common import ProblemDetail
from backend.app.schemas.job import JobAlertInboxRead, JobAlertReadState, JobAlertReadUpdate
from backend.app.services.job_alerts import JobAlertInboxService


def reject_alert_query(request: Request) -> None:
    if request.query_params:
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


router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
    dependencies=[Depends(reject_alert_query)],
    responses={
        401: {"model": ProblemDetail},
        403: {"model": ProblemDetail},
        404: {"model": ProblemDetail},
        422: {"model": ProblemDetail},
    },
)


@router.get("", response_model=JobAlertInboxRead)
def list_alerts(
    response: Response,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
):
    response.headers["Cache-Control"] = "no-store"
    return JobAlertInboxService.list(user.id, uow)


@router.patch("/{id}", response_model=JobAlertReadState)
def mark_alert_read(
    id: UUID,
    payload: JobAlertReadUpdate,
    response: Response,
    authenticated=Depends(require_csrf),
    uow: UnitOfWork = Depends(get_uow),
):
    del payload
    response.headers["Cache-Control"] = "no-store"
    return JobAlertInboxService.mark_read(authenticated[0].id, id, uow)
