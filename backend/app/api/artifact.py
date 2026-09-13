"""Authenticated linked Resume CRUD with existing ownership/CSRF conventions."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from backend.app.api.deps import get_current_user, get_uow, require_csrf
from backend.app.api.employment import reject_owner_query
from backend.app.schemas.artifact import ArtifactCreate, ArtifactRead, ArtifactUpdate
from backend.app.schemas.common import ProblemDetail
from backend.app.services.artifact import ArtifactService

router = APIRouter(
    prefix="/artifacts",
    tags=["career-artifacts"],
    dependencies=[Depends(reject_owner_query)],
    responses={
        401: {"model": ProblemDetail},
        403: {"model": ProblemDetail},
        404: {"model": ProblemDetail},
    },
)


def no_store(response):
    response.headers["Cache-Control"] = "no-store"


@router.get("", response_model=list[ArtifactRead])
def artifacts(response: Response, user=Depends(get_current_user), uow=Depends(get_uow)):
    no_store(response)
    return ArtifactService.list(user.id, uow)


@router.get("/{id}", response_model=ArtifactRead)
def artifact(id: UUID, response: Response, user=Depends(get_current_user), uow=Depends(get_uow)):
    no_store(response)
    return ArtifactService.get(user.id, id, uow)


@router.post("", response_model=ArtifactRead, status_code=201)
def create(
    payload: ArtifactCreate,
    response: Response,
    authenticated=Depends(require_csrf),
    uow=Depends(get_uow),
):
    no_store(response)
    return ArtifactService.save(authenticated[0].id, payload, uow)


@router.patch("/{id}", response_model=ArtifactRead)
def update(
    id: UUID,
    payload: ArtifactUpdate,
    response: Response,
    authenticated=Depends(require_csrf),
    uow=Depends(get_uow),
):
    no_store(response)
    try:
        return ArtifactService.save(authenticated[0].id, payload, uow, id)
    except ValidationError as error:
        raise RequestValidationError(
            [{**item, "loc": ("body", *item["loc"])} for item in error.errors(include_url=False)]
        ) from error


@router.delete("/{id}", status_code=204)
def delete(id: UUID, authenticated=Depends(require_csrf), uow=Depends(get_uow)):
    ArtifactService.delete(authenticated[0].id, id, uow)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
