"""Authenticated shared-job browsing; no writes, matching, or applications."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError

from backend.app.api.deps import get_current_user, get_uow, require_csrf
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.models.user import User
from backend.app.schemas.common import ProblemDetail
from backend.app.schemas.fit import FitAnalysisRead
from backend.app.schemas.job import (
    JobUserStateRead,
    JobUserStateUpdate,
    PublicJobDetailRead,
    PublicJobSearchRead,
)
from backend.app.schemas.resume_alignment import ResumeAlignmentRead
from backend.app.schemas.resume_draft import ResumeTailoringDraftRead
from backend.app.schemas.resume_plan import ResumeImprovementPlanRead
from backend.app.schemas.resume_review import (
    ResumeTailoringReviewCreate,
    ResumeTailoringReviewItemUpdate,
    ResumeTailoringReviewRead,
)
from backend.app.schemas.skill_gap import SkillGapAnalysisRead
from backend.app.services.fit import FitService
from backend.app.services.job import JobSearch, JobSearchValidationError, JobService
from backend.app.services.job_discovery import JobInteractionService
from backend.app.services.resume_alignment import ResumeAlignmentService
from backend.app.services.resume_draft import ResumeTailoringDraftService
from backend.app.services.resume_plan import ResumeImprovementPlanService
from backend.app.services.resume_review import ResumeTailoringReviewService
from backend.app.services.skill_gap import SkillGapService

_LIST_QUERY_FIELDS = frozenset(
    {
        "keyword",
        "query",
        "location",
        "company",
        "requirement",
        "employment_type",
        "type",
        "job_type",
        "work_mode",
        "role",
        "country",
        "region",
        "city",
        "recency",
        "view",
        "page",
        "page_size",
        "sort",
    }
)
_RESUME_VERSION_QUERY_FIELDS = frozenset({"resume_version_id"})
_MULTI_VALUE_QUERY_FIELDS = frozenset(
    {
        "employment_type",
        "type",
        "job_type",
        "work_mode",
        "role",
        "country",
        "region",
        "city",
    }
)


def reject_invalid_job_query(request: Request) -> None:
    route_path = getattr(request.scope.get("route"), "path", "")
    if route_path in {
        "/jobs/{id}/resume-alignment",
        "/jobs/{id}/gaps",
        "/jobs/{id}/resume-plan",
        "/jobs/{id}/resume-draft",
    } or (route_path == "/jobs/{id}/resume-reviews" and request.method == "GET"):
        allowed = _RESUME_VERSION_QUERY_FIELDS
    elif "id" in request.path_params:
        allowed = frozenset()
    else:
        allowed = _LIST_QUERY_FIELDS
    unexpected = sorted(set(request.query_params) - allowed)
    repeated = sorted(
        name
        for name in set(request.query_params)
        if len(request.query_params.getlist(name)) != 1
        and name not in _MULTI_VALUE_QUERY_FIELDS
    )
    invalid = unexpected + [name for name in repeated if name not in unexpected]
    if invalid:
        raise RequestValidationError(
            [
                {
                    "type": "extra_forbidden",
                    "loc": ("query", name),
                    "msg": "Extra inputs are not permitted",
                }
                for name in invalid
            ]
        )


router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(reject_invalid_job_query)],
    responses={
        401: {"model": ProblemDetail},
        403: {"model": ProblemDetail},
        404: {"model": ProblemDetail},
        409: {"model": ProblemDetail},
    },
)


@router.get("", response_model=PublicJobSearchRead)
def list_jobs(
    keyword: str | None = Query(None, max_length=100),
    query: str | None = Query(None, max_length=100),
    location: str | None = Query(None, max_length=100),
    company: str | None = Query(None, max_length=100),
    requirement: str | None = Query(None, max_length=100),
    employment_type: list[str] = Query(default=[]),
    job_type: list[str] = Query(default=[], alias="type"),
    structured_job_type: list[str] = Query(default=[], alias="job_type"),
    work_mode: list[str] = Query(default=[]),
    role: list[str] = Query(default=[]),
    country: list[str] = Query(default=[]),
    region: list[str] = Query(default=[]),
    city: list[str] = Query(default=[]),
    recency: str | None = Query(None, max_length=10),
    view: Literal["all", "saved", "hidden"] = "all",
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(10, ge=1, le=50),
    sort: Literal["newest", "oldest", "title_asc", "title_desc"] = "newest",
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
):
    try:
        criteria = JobSearch.from_request(
            keyword=keyword,
            query=query,
            location=location,
            company=company,
            requirement=requirement,
            employment_type=employment_type,
            job_type=job_type,
            type=structured_job_type,
            work_mode=work_mode,
            role=role,
            country=country,
            region=region,
            city=city,
            recency=recency,
            view=view,
            page=page,
            page_size=page_size,
            sort=sort,
        )
    except JobSearchValidationError as exc:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("query",),
                    "msg": str(exc),
                }
            ]
        ) from exc
    return JobService.list_active(criteria, uow, user.id)


@router.get("/{id}/fit", response_model=FitAnalysisRead)
def get_job_fit(
    id: UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
):
    """Return the session owner's recorded evidence coverage for one active job."""

    return FitService.analyze(id, user.id, uow)


@router.get("/{id}/resume-alignment", response_model=ResumeAlignmentRead)
def get_job_resume_alignment(
    id: UUID,
    resume_version_id: UUID = Query(...),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
):
    """Return exact-version evidence coverage for one active job without writing facts."""

    return ResumeAlignmentService.analyze(id, resume_version_id, user.id, uow)


@router.get("/{id}/gaps", response_model=SkillGapAnalysisRead)
def get_job_skill_gaps(
    id: UUID,
    resume_version_id: UUID = Query(...),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
):
    """Return read-only, exact-evidence gaps for one owned resume version."""

    return SkillGapService.analyze(id, resume_version_id, user.id, uow)


@router.get("/{id}/resume-plan", response_model=ResumeImprovementPlanRead)
def get_resume_improvement_plan(
    id: UUID,
    resume_version_id: UUID = Query(...),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
):
    """Return conservative, read-only actions for one owned resume version."""

    return ResumeImprovementPlanService.analyze(id, resume_version_id, user.id, uow)


@router.get("/{id}/resume-draft", response_model=ResumeTailoringDraftRead)
def get_resume_tailoring_draft(
    id: UUID,
    resume_version_id: UUID = Query(...),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
):
    """Return non-persistent, source-cited draft fragments for one owned resume version."""

    return ResumeTailoringDraftService.analyze(id, resume_version_id, user.id, uow)


@router.get("/{id}/resume-reviews", response_model=ResumeTailoringReviewRead)
def get_resume_tailoring_review(
    id: UUID,
    resume_version_id: UUID = Query(...),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
):
    """Read this user's saved snapshot without regenerating Phase 16 suggestions."""

    return ResumeTailoringReviewService.get(user.id, id, resume_version_id, uow)


@router.post("/{id}/resume-reviews", response_model=ResumeTailoringReviewRead, status_code=201)
def create_resume_tailoring_review(
    id: UUID,
    payload: ResumeTailoringReviewCreate,
    authenticated=Depends(require_csrf),
    uow: UnitOfWork = Depends(get_uow),
):
    """Save the current safe Phase 16 suggestions as an explicit user review."""

    return ResumeTailoringReviewService.create(authenticated[0].id, id, payload, uow)


@router.patch(
    "/{id}/resume-reviews/{review_id}/items/{item_id}",
    response_model=ResumeTailoringReviewRead,
)
def update_resume_tailoring_review_item(
    id: UUID,
    review_id: UUID,
    item_id: UUID,
    payload: ResumeTailoringReviewItemUpdate,
    authenticated=Depends(require_csrf),
    uow: UnitOfWork = Depends(get_uow),
):
    """Persist a decision or separate user wording while the review is still editable."""

    return ResumeTailoringReviewService.update_item(
        authenticated[0].id, id, review_id, item_id, payload, uow
    )


@router.post("/{id}/resume-reviews/{review_id}/finalize", response_model=ResumeTailoringReviewRead)
def finalize_resume_tailoring_review(
    id: UUID,
    review_id: UUID,
    authenticated=Depends(require_csrf),
    uow: UnitOfWork = Depends(get_uow),
):
    """Make an explicitly completed review immutable without changing a resume version."""

    return ResumeTailoringReviewService.finalize(authenticated[0].id, id, review_id, uow)


@router.patch("/{id}/state", response_model=JobUserStateRead)
def update_job_state(
    id: UUID,
    payload: JobUserStateUpdate,
    authenticated=Depends(require_csrf),
    uow: UnitOfWork = Depends(get_uow),
):
    """Persist one owner's Save/Hide/Viewed state without changing the job."""

    return JobInteractionService.update(authenticated[0].id, id, payload, uow)


@router.get("/{id}", response_model=PublicJobDetailRead)
def get_job(
    id: UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_uow),
):
    return JobService.get_active(id, uow, user.id)
