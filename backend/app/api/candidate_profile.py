"""Authenticated derived candidate-profile endpoint."""

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError

from backend.app.api.deps import get_current_user, get_uow
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.models.user import User
from backend.app.schemas.candidate_profile import CandidateProfileRead
from backend.app.schemas.common import ProblemDetail
from backend.app.services.candidate_profile import CandidateProfileService


def reject_owner_query(request: Request) -> None:
    if "user_id" in request.query_params:
        raise RequestValidationError(
            [
                {
                    "type": "extra_forbidden",
                    "loc": ("query", "user_id"),
                    "msg": "Extra inputs are not permitted",
                }
            ]
        )


router = APIRouter(
    prefix="/profile/candidate",
    tags=["candidate-profile"],
    dependencies=[Depends(reject_owner_query)],
    responses={401: {"model": ProblemDetail}},
)


@router.get("", response_model=CandidateProfileRead)
def get_candidate_profile(
    response: Response,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
):
    response.headers["Cache-Control"] = "no-store"
    return CandidateProfileService.read(user.id, uow)
