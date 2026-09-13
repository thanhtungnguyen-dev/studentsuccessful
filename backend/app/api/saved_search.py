"""Private structured saved-search routes for the canonical jobs feed."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.exceptions import RequestValidationError

from backend.app.api.deps import get_current_user, get_uow, require_csrf
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.models.user import User
from backend.app.schemas.common import ProblemDetail
from backend.app.schemas.job import (
    SavedJobSearchCreate,
    SavedJobSearchRead,
    SavedJobSearchUpdate,
)
from backend.app.services.job_discovery import SavedJobSearchService


def reject_saved_search_query(request: Request) -> None:
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
    prefix="/saved-searches",
    tags=["saved searches"],
    dependencies=[Depends(reject_saved_search_query)],
    responses={
        401: {"model": ProblemDetail},
        403: {"model": ProblemDetail},
        404: {"model": ProblemDetail},
        422: {"model": ProblemDetail},
    },
)


@router.get("", response_model=list[SavedJobSearchRead])
def list_saved_searches(
    response: Response,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
):
    response.headers["Cache-Control"] = "no-store"
    return SavedJobSearchService.list(user.id, uow)


@router.post("", response_model=SavedJobSearchRead, status_code=status.HTTP_201_CREATED)
def create_saved_search(
    payload: SavedJobSearchCreate,
    response: Response,
    authenticated=Depends(require_csrf),
    uow: UnitOfWork = Depends(get_uow),
):
    response.headers["Cache-Control"] = "no-store"
    return SavedJobSearchService.create(authenticated[0].id, payload, uow)


@router.get("/{id}", response_model=SavedJobSearchRead)
def get_saved_search(
    id: UUID,
    response: Response,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
):
    response.headers["Cache-Control"] = "no-store"
    return SavedJobSearchService.get(user.id, id, uow)


@router.patch("/{id}", response_model=SavedJobSearchRead)
def update_saved_search(
    id: UUID,
    payload: SavedJobSearchUpdate,
    response: Response,
    authenticated=Depends(require_csrf),
    uow: UnitOfWork = Depends(get_uow),
):
    response.headers["Cache-Control"] = "no-store"
    return SavedJobSearchService.update(authenticated[0].id, id, payload, uow)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_search(
    id: UUID,
    authenticated=Depends(require_csrf),
    uow: UnitOfWork = Depends(get_uow),
):
    SavedJobSearchService.delete(authenticated[0].id, id, uow)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Cache-Control": "no-store"})
