"""Approved preferences and read-only catalog routes."""
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError

from backend.app.api.deps import get_current_user, get_uow, require_csrf
from backend.app.models.taxonomy import Company, Industry, Location, Role, Skill
from backend.app.schemas.common import ProblemDetail
from backend.app.schemas.preferences import CatalogItem, CatalogLocation, Preferences
from backend.app.services.preferences import CatalogService, PreferencesService


def reject_owner(request: Request):
    if "user_id" in request.query_params:
        raise RequestValidationError([{"type": "extra_forbidden", "loc": ("query", "user_id"), "msg": "Extra inputs are not permitted"}])


router = APIRouter(dependencies=[Depends(reject_owner)], responses={401: {"model": ProblemDetail}})


@router.get("/preferences", response_model=Preferences, tags=["preferences"])
def get_preferences(response: Response, user=Depends(get_current_user), uow=Depends(get_uow)):
    response.headers["Cache-Control"] = "no-store"
    return PreferencesService.get(user.id, uow)


@router.put("/preferences", response_model=Preferences, tags=["preferences"], responses={403: {"model": ProblemDetail}, 422: {"model": ProblemDetail}})
def replace_preferences(payload: Preferences, response: Response, authenticated=Depends(require_csrf), uow=Depends(get_uow)):
    response.headers["Cache-Control"] = "no-store"
    return PreferencesService.replace(authenticated[0].id, payload, uow)


@router.get("/catalog/roles", response_model=list[CatalogItem], tags=["catalog"])
def roles(q: str | None = None, active: bool = True, user=Depends(get_current_user), uow=Depends(get_uow)):
    return CatalogService.list(Role, uow, q=q, active=active)


@router.get("/catalog/skills", response_model=list[CatalogItem], tags=["catalog"])
def skills(q: str | None = None, category: str | None = None, user=Depends(get_current_user), uow=Depends(get_uow)):
    return CatalogService.list(Skill, uow, q=q, category=category, active=True)


@router.get("/catalog/industries", response_model=list[CatalogItem], tags=["catalog"])
def industries(user=Depends(get_current_user), uow=Depends(get_uow)):
    return CatalogService.list(Industry, uow)


@router.get("/catalog/companies", response_model=list[CatalogItem], tags=["catalog"])
def companies(q: str | None = None, user=Depends(get_current_user), uow=Depends(get_uow)):
    return CatalogService.list(Company, uow, q=q)


@router.get("/catalog/locations", response_model=list[CatalogLocation], tags=["catalog"])
def locations(q: str | None = None, country_code: str | None = Query(None, pattern="^[A-Za-z]{2}$"), user=Depends(get_current_user), uow=Depends(get_uow)):
    return CatalogService.list(Location, uow, location=True, q=q, country_code=country_code)
