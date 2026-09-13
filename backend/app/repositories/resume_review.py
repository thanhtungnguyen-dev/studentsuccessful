"""Owned resume-review queries. Repositories never commit transactions."""

from sqlalchemy import select

from backend.app.models.resume_review import ResumeTailoringReview, ResumeTailoringReviewItem


class ResumeTailoringReviewRepository:
    def __init__(self, session):
        self.session = session

    def for_context(self, owner, job_id, resume_version_id):
        return self.session.scalar(
            select(ResumeTailoringReview).where(
                ResumeTailoringReview.user_id == owner,
                ResumeTailoringReview.job_id == job_id,
                ResumeTailoringReview.source_resume_version_id == resume_version_id,
            )
        )

    def owned(self, owner, job_id, review_id, lock=False):
        query = select(ResumeTailoringReview).where(
            ResumeTailoringReview.user_id == owner,
            ResumeTailoringReview.job_id == job_id,
            ResumeTailoringReview.id == review_id,
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(query)

    def items(self, review_id):
        return list(
            self.session.scalars(
                select(ResumeTailoringReviewItem)
                .where(ResumeTailoringReviewItem.review_id == review_id)
                .order_by(ResumeTailoringReviewItem.ordinal, ResumeTailoringReviewItem.id)
            )
        )

    def item_for_review(self, review_id, item_id, lock=False):
        query = select(ResumeTailoringReviewItem).where(
            ResumeTailoringReviewItem.review_id == review_id,
            ResumeTailoringReviewItem.id == item_id,
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(query)
