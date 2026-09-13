"""Persisted review decisions over a stable Phase 16 draft snapshot."""

from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.models.base import utc_now
from backend.app.models.resume_review import ResumeTailoringReview, ResumeTailoringReviewItem
from backend.app.repositories.resume_review import ResumeTailoringReviewRepository
from backend.app.schemas.candidate_profile import CandidateSkillSourceRead
from backend.app.schemas.resume_review import (
    ResumeTailoringReviewCreate,
    ResumeTailoringReviewItemRead,
    ResumeTailoringReviewItemUpdate,
    ResumeTailoringReviewRead,
)
from backend.app.services.resume_draft import ResumeTailoringDraftService


class ResumeTailoringReviewService:
    """Creates explicit review facts without creating or changing candidate evidence."""

    @staticmethod
    def _not_found():
        raise StudentSuccessfulException(
            404,
            "RESUME_TAILORING_REVIEW_NOT_FOUND",
            "Resume tailoring review not found",
        )

    @staticmethod
    def _item_read(row: ResumeTailoringReviewItem) -> ResumeTailoringReviewItemRead:
        return ResumeTailoringReviewItemRead(
            id=row.id,
            ordinal=row.ordinal,
            category=row.category,
            action=row.action,
            requirement_id=row.requirement_id,
            name=row.requirement_name,
            importance=row.importance,
            description=row.requirement_description,
            original_draft_text=row.original_draft_text,
            reason=row.reason,
            limitation=row.limitation,
            provenance=[CandidateSkillSourceRead.model_validate(source) for source in row.provenance],
            decision=row.decision,
            user_edited_text=row.user_edited_text,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @classmethod
    def _read(
        cls, row: ResumeTailoringReview, repository: ResumeTailoringReviewRepository
    ) -> ResumeTailoringReviewRead:
        return ResumeTailoringReviewRead(
            id=row.id,
            status=row.status,
            job_id=row.job_id,
            job_title=row.job_title_snapshot,
            company_name=row.company_name_snapshot,
            source_resume_version_id=row.source_resume_version_id,
            resume_title=row.resume_title_snapshot,
            resume_version_number=row.resume_version_number_snapshot,
            items=[cls._item_read(item) for item in repository.items(row.id)],
            created_at=row.created_at,
            updated_at=row.updated_at,
            finalized_at=row.finalized_at,
        )

    @classmethod
    def get(cls, owner, job_id, resume_version_id, uow) -> ResumeTailoringReviewRead:
        repository = ResumeTailoringReviewRepository(uow.session)
        review = repository.for_context(owner, job_id, resume_version_id)
        if review is None:
            cls._not_found()
        return cls._read(review, repository)

    @classmethod
    def create(
        cls, owner, job_id, payload: ResumeTailoringReviewCreate, uow
    ) -> ResumeTailoringReviewRead:
        repository = ResumeTailoringReviewRepository(uow.session)
        existing = repository.for_context(owner, job_id, payload.resume_version_id)
        if existing is not None:
            return cls._read(existing, repository)

        draft = ResumeTailoringDraftService.analyze(
            job_id, payload.resume_version_id, owner, uow
        )
        review = ResumeTailoringReview(
            user_id=owner,
            job_id=draft.job_id,
            source_resume_version_id=draft.resume_version_id,
            job_title_snapshot=draft.job_title,
            company_name_snapshot=draft.company_name,
            resume_title_snapshot=draft.resume_title,
            resume_version_number_snapshot=draft.resume_version_number,
        )
        uow.session.add(review)
        uow.session.flush()
        for ordinal, draft_item in enumerate(draft.draft_suggestions):
            if not draft_item.draft_text:
                raise RuntimeError("Phase 16 draft suggestion missing draft text")
            uow.session.add(
                ResumeTailoringReviewItem(
                    review_id=review.id,
                    ordinal=ordinal,
                    category=draft_item.category,
                    action=draft_item.action,
                    requirement_id=draft_item.requirement_id,
                    requirement_name=draft_item.name,
                    importance=draft_item.importance,
                    requirement_description=draft_item.description,
                    original_draft_text=draft_item.draft_text,
                    reason=draft_item.reason,
                    limitation=draft_item.limitation,
                    provenance=[source.model_dump(mode="json") for source in draft_item.sources],
                )
            )
        uow.session.flush()
        result = cls._read(review, repository)
        uow.commit()
        return result

    @classmethod
    def update_item(
        cls, owner, job_id, review_id, item_id, payload: ResumeTailoringReviewItemUpdate, uow
    ) -> ResumeTailoringReviewRead:
        repository = ResumeTailoringReviewRepository(uow.session)
        review = repository.owned(owner, job_id, review_id, lock=True)
        if review is None:
            cls._not_found()
        if review.status == "FINALIZED":
            raise StudentSuccessfulException(
                409,
                "RESUME_TAILORING_REVIEW_FINALIZED",
                "Finalized resume tailoring reviews cannot be changed",
            )
        item = repository.item_for_review(review.id, item_id, lock=True)
        if item is None:
            cls._not_found()
        if "decision" in payload.model_fields_set:
            item.decision = payload.decision
        if "user_edited_text" in payload.model_fields_set:
            item.user_edited_text = payload.user_edited_text
        uow.session.flush()
        result = cls._read(review, repository)
        uow.commit()
        return result

    @classmethod
    def finalize(cls, owner, job_id, review_id, uow) -> ResumeTailoringReviewRead:
        repository = ResumeTailoringReviewRepository(uow.session)
        review = repository.owned(owner, job_id, review_id, lock=True)
        if review is None:
            cls._not_found()
        if review.status == "FINALIZED":
            return cls._read(review, repository)
        if any(item.decision == "PENDING" for item in repository.items(review.id)):
            raise StudentSuccessfulException(
                409,
                "RESUME_TAILORING_REVIEW_HAS_PENDING_ITEMS",
                "Choose ACCEPTED or REJECTED for every review item before finalizing",
            )
        review.status = "FINALIZED"
        review.finalized_at = utc_now()
        uow.session.flush()
        result = cls._read(review, repository)
        uow.commit()
        return result
