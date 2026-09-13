"""Private Save/Hide/Viewed state and structured saved searches."""

import re

from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.models.base import utc_now
from backend.app.models.job import SavedJobSearch, SavedSearchAlertMode, UserJobState
from backend.app.repositories.job_discovery import JobDiscoveryRepository
from backend.app.schemas.job import (
    JobUserStateRead,
    JobUserStateUpdate,
    SavedJobSearchCreate,
    SavedJobSearchRead,
    SavedJobSearchUpdate,
)
from backend.app.services.job import JobSearch, JobSearchValidationError

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _saved_search_name(value: str) -> str:
    if _CONTROL.search(value):
        raise StudentSuccessfulException(
            422,
            "INVALID_SAVED_SEARCH",
            "Saved search name must not contain control characters",
        )
    normalized = " ".join(value.split())
    if not normalized:
        raise StudentSuccessfulException(
            422,
            "INVALID_SAVED_SEARCH",
            "Saved search name is required",
        )
    return normalized


def _normalized_criteria(criteria):
    try:
        return JobSearch.from_saved_criteria(criteria).to_saved_criteria()
    except JobSearchValidationError as exc:
        raise StudentSuccessfulException(
            422,
            "INVALID_SAVED_SEARCH_CRITERIA",
            str(exc),
        ) from exc


class JobInteractionService:
    @staticmethod
    def update(user_id, job_id, payload: JobUserStateUpdate, uow) -> JobUserStateRead:
        repository = JobDiscoveryRepository(uow.session)
        if repository.active_canonical_job_for_update(job_id) is None:
            raise StudentSuccessfulException(404, "JOB_NOT_FOUND", "Job not found")
        state = repository.user_state_for_update(user_id, job_id)
        saved = state.saved if state is not None else False
        hidden = state.hidden if state is not None else False
        viewed_at = state.viewed_at if state is not None else None
        if payload.saved is not None:
            saved = payload.saved
        if payload.hidden is not None:
            hidden = payload.hidden
        if payload.viewed:
            viewed_at = viewed_at or utc_now()

        if state is None and (saved or hidden or viewed_at is not None):
            state = repository.add_user_state(
                UserJobState(
                    user_id=user_id,
                    canonical_job_id=job_id,
                    saved=saved,
                    hidden=hidden,
                    viewed_at=viewed_at,
                )
            )
            uow.session.flush()
        elif state is not None:
            state.saved = saved
            state.hidden = hidden
            state.viewed_at = viewed_at
            state.updated_at = utc_now()
            if not saved and not hidden and viewed_at is None:
                repository.delete_user_state(state)
            else:
                uow.session.flush()

        result = JobUserStateRead(
            job_id=job_id,
            saved=saved,
            hidden=hidden,
            viewed_at=viewed_at,
            unseen=viewed_at is None,
        )
        uow.commit()
        return result


class SavedJobSearchService:
    @staticmethod
    def _read(saved_search: SavedJobSearch) -> SavedJobSearchRead:
        return SavedJobSearchRead(
            id=saved_search.id,
            name=saved_search.name,
            criteria=saved_search.criteria,
            alert_mode=saved_search.alert_mode,
            alert_enabled_at=saved_search.alert_enabled_at,
            created_at=saved_search.created_at,
            updated_at=saved_search.updated_at,
        )

    @staticmethod
    def _owned(repository: JobDiscoveryRepository, user_id, search_id, *, lock=False):
        saved_search = repository.saved_search(user_id, search_id, lock=lock)
        if saved_search is None:
            raise StudentSuccessfulException(
                404,
                "SAVED_SEARCH_NOT_FOUND",
                "Saved search not found",
            )
        return saved_search

    @classmethod
    def list(cls, user_id, uow) -> list[SavedJobSearchRead]:
        repository = JobDiscoveryRepository(uow.session)
        return [cls._read(saved_search) for saved_search in repository.list_saved_searches(user_id)]

    @classmethod
    def get(cls, user_id, search_id, uow) -> SavedJobSearchRead:
        return cls._read(cls._owned(JobDiscoveryRepository(uow.session), user_id, search_id))

    @classmethod
    def create(cls, user_id, payload: SavedJobSearchCreate, uow) -> SavedJobSearchRead:
        repository = JobDiscoveryRepository(uow.session)
        now = utc_now()
        alert_enabled = payload.alert_mode != SavedSearchAlertMode.OFF
        saved_search = repository.add_saved_search(
            SavedJobSearch(
                user_id=user_id,
                name=_saved_search_name(payload.name),
                criteria=_normalized_criteria(payload.criteria).model_dump(),
                alert_mode=payload.alert_mode,
                alert_enabled_at=now if alert_enabled else None,
                alert_watermark_at=now if alert_enabled else None,
                alert_evaluated_at=now if alert_enabled else None,
            )
        )
        uow.session.flush()
        result = cls._read(saved_search)
        uow.commit()
        return result

    @classmethod
    def update(cls, user_id, search_id, payload: SavedJobSearchUpdate, uow) -> SavedJobSearchRead:
        repository = JobDiscoveryRepository(uow.session)
        saved_search = cls._owned(repository, user_id, search_id, lock=True)
        now = utc_now()
        criteria_changed = False
        if payload.name is not None:
            saved_search.name = _saved_search_name(payload.name)
        if payload.criteria is not None:
            normalized_criteria = _normalized_criteria(payload.criteria).model_dump()
            criteria_changed = normalized_criteria != saved_search.criteria
            saved_search.criteria = normalized_criteria

        requested_mode = (
            payload.alert_mode
            if "alert_mode" in payload.model_fields_set
            else saved_search.alert_mode
        )
        was_enabled = saved_search.alert_mode != SavedSearchAlertMode.OFF
        will_be_enabled = requested_mode != SavedSearchAlertMode.OFF
        if not will_be_enabled:
            saved_search.alert_mode = SavedSearchAlertMode.OFF
            saved_search.alert_enabled_at = None
            saved_search.alert_watermark_at = None
            saved_search.alert_evaluated_at = None
            saved_search.alert_evaluated_job_id = None
        elif not was_enabled or criteria_changed:
            # A fresh activation boundary prevents backfill after enabling,
            # re-enabling, or changing the structured criteria.
            saved_search.alert_mode = requested_mode
            saved_search.alert_enabled_at = now
            saved_search.alert_watermark_at = now
            saved_search.alert_evaluated_at = now
            saved_search.alert_evaluated_job_id = None
        else:
            # Delivery-mode changes preserve the current subscription boundary.
            saved_search.alert_mode = requested_mode
        saved_search.updated_at = now
        uow.session.flush()
        result = cls._read(saved_search)
        uow.commit()
        return result

    @classmethod
    def delete(cls, user_id, search_id, uow) -> None:
        repository = JobDiscoveryRepository(uow.session)
        repository.delete_saved_search(cls._owned(repository, user_id, search_id, lock=True))
        uow.commit()
