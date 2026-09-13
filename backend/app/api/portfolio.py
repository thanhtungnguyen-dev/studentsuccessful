"""Authenticated factual skill replacement and owned project CRUD."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from backend.app.api.deps import get_current_user, get_uow, require_csrf
from backend.app.api.employment import reject_owner_query
from backend.app.schemas.common import ProblemDetail
from backend.app.schemas.portfolio import ProjectCreate, ProjectRead, ProjectUpdate, SkillSelection
from backend.app.services.portfolio import PortfolioService

router = APIRouter(
    prefix="/profile",
    tags=["skills-projects"],
    dependencies=[Depends(reject_owner_query)],
    responses={
        401: {"model": ProblemDetail},
        403: {"model": ProblemDetail},
        404: {"model": ProblemDetail},
    },
)


def no_store(response):
    response.headers["Cache-Control"] = "no-store"


@router.get("/skills", response_model=SkillSelection)
def skills(response: Response, user=Depends(get_current_user), uow=Depends(get_uow)):
    no_store(response)
    return PortfolioService.skills(user.id, uow)


@router.put("/skills", response_model=SkillSelection)
def save_skills(
    payload: SkillSelection,
    response: Response,
    authenticated=Depends(require_csrf),
    uow=Depends(get_uow),
):
    no_store(response)
    return PortfolioService.skills(authenticated[0].id, uow, payload)


@router.get("/projects", response_model=list[ProjectRead])
def projects(response: Response, user=Depends(get_current_user), uow=Depends(get_uow)):
    no_store(response)
    return PortfolioService.list_projects(user.id, uow)


@router.get("/projects/{id}", response_model=ProjectRead)
def project(id: UUID, response: Response, user=Depends(get_current_user), uow=Depends(get_uow)):
    no_store(response)
    return PortfolioService.list_projects(user.id, uow, id)


@router.post("/projects", response_model=ProjectRead, status_code=201)
def create_project(
    payload: ProjectCreate,
    response: Response,
    authenticated=Depends(require_csrf),
    uow=Depends(get_uow),
):
    no_store(response)
    return PortfolioService.save_project(authenticated[0].id, payload, uow)


@router.patch("/projects/{id}", response_model=ProjectRead)
def update_project(
    id: UUID,
    payload: ProjectUpdate,
    response: Response,
    authenticated=Depends(require_csrf),
    uow=Depends(get_uow),
):
    no_store(response)
    try:
        return PortfolioService.save_project(authenticated[0].id, payload, uow, id)
    except ValidationError as error:
        raise RequestValidationError(
            [{**item, "loc": ("body", *item["loc"])} for item in error.errors(include_url=False)]
        ) from error


@router.delete("/projects/{id}", status_code=204)
def delete_project(id: UUID, authenticated=Depends(require_csrf), uow=Depends(get_uow)):
    PortfolioService.delete_project(authenticated[0].id, id, uow)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
