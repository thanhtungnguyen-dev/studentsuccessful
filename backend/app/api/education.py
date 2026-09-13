"""Approved nested Education API; session ownership and existing CSRF protection."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from backend.app.api.deps import get_current_user, get_uow, require_csrf
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.models.user import User
from backend.app.schemas.common import ProblemDetail
from backend.app.schemas.education import EducationCreate, EducationRead, EducationUpdate
from backend.app.services.education import EducationService


def reject_owner_query(request: Request):
    if "user_id" in request.query_params:
        raise RequestValidationError([{"type": "extra_forbidden", "loc": ("query", "user_id"), "msg": "Extra inputs are not permitted"}])


router = APIRouter(prefix="/profile/education", tags=["education"], dependencies=[Depends(reject_owner_query)], responses={401: {"model": ProblemDetail}})
MUTATION_ERRORS = {403: {"model": ProblemDetail}, 404: {"model": ProblemDetail}}


@router.get("", response_model=list[EducationRead])
def list_education(response: Response, user: User = Depends(get_current_user), uow: UnitOfWork = Depends(get_uow)):
    response.headers["Cache-Control"] = "no-store"
    return EducationService.list_for_user(user.id, uow)


@router.post("", response_model=EducationRead, status_code=201, responses={403: {"model": ProblemDetail}})
def create_education(payload: EducationCreate, response: Response, authenticated=Depends(require_csrf), uow: UnitOfWork = Depends(get_uow)):
    response.headers["Cache-Control"] = "no-store"
    return EducationService.create(authenticated[0].id, payload, uow)


@router.patch("/{id}", response_model=EducationRead, responses=MUTATION_ERRORS)
def update_education(id: UUID, payload: EducationUpdate, response: Response, authenticated=Depends(require_csrf), uow: UnitOfWork = Depends(get_uow)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return EducationService.update(authenticated[0].id, id, payload, uow)
    except ValidationError as error:
        raise RequestValidationError([{**item, "loc": ("body", *item["loc"])} for item in error.errors(include_url=False)]) from error


@router.delete("/{id}", status_code=204, responses=MUTATION_ERRORS)
def delete_education(id: UUID, authenticated=Depends(require_csrf), uow: UnitOfWork = Depends(get_uow)):
    EducationService.delete(authenticated[0].id, id, uow)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
