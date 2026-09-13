"""Session-owned profile read and CSRF-protected partial update."""

from fastapi import APIRouter, Depends, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from backend.app.api.deps import get_current_user, get_uow, require_csrf
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.models.user import User
from backend.app.schemas.common import ProblemDetail
from backend.app.schemas.profile import ProfileRead, ProfileUpdate
from backend.app.services.profile import ApplicationProfileService

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileRead | None, responses={401: {"model": ProblemDetail}})
def get_profile(
    response: Response,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
):
    """Read only this user's submitted facts; null means no profile has been saved."""
    response.headers["Cache-Control"] = "no-store"
    return ApplicationProfileService.read(user.id, uow)


@router.patch("", response_model=ProfileRead, responses={401: {"model": ProblemDetail}, 403: {"model": ProblemDetail}})
def update_profile(
    payload: ProfileUpdate,
    response: Response,
    authenticated=Depends(require_csrf),
    uow: UnitOfWork = Depends(get_uow),
):
    """Omit to preserve; null clears optional fields. First save requires both legal names."""
    response.headers["Cache-Control"] = "no-store"
    user, _ = authenticated
    try:
        return ApplicationProfileService.update(user.id, payload, uow)
    except ValidationError as error:
        raise RequestValidationError([
            {**item, "loc": ("body", *item["loc"])}
            for item in error.errors(include_url=False)
        ]) from error
