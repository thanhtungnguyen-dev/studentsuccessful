"""Private state and saved-search persistence for canonical job discovery."""

from sqlalchemy import select

from backend.app.models.job import JobLifecycle, NormalizedJob, SavedJobSearch, UserJobState


class JobDiscoveryRepository:
    def __init__(self, session):
        self.session = session

    def active_canonical_job_for_update(self, job_id):
        return self.session.scalar(
            select(NormalizedJob.id)
            .where(
                NormalizedJob.id == job_id,
                NormalizedJob.is_active.is_(True),
                NormalizedJob.lifecycle != JobLifecycle.CLOSED,
            )
            .with_for_update()
        )

    def user_state_for_update(self, user_id, job_id):
        return self.session.scalar(
            select(UserJobState)
            .where(
                UserJobState.user_id == user_id,
                UserJobState.canonical_job_id == job_id,
            )
            .with_for_update()
        )

    def add_user_state(self, state: UserJobState) -> UserJobState:
        self.session.add(state)
        return state

    def delete_user_state(self, state: UserJobState) -> None:
        self.session.delete(state)

    def list_saved_searches(self, user_id):
        return list(
            self.session.scalars(
                select(SavedJobSearch)
                .where(SavedJobSearch.user_id == user_id)
                .order_by(SavedJobSearch.updated_at.desc(), SavedJobSearch.id.desc())
            )
        )

    def saved_search(self, user_id, search_id, *, lock: bool = False):
        query = select(SavedJobSearch).where(
            SavedJobSearch.id == search_id,
            SavedJobSearch.user_id == user_id,
        )
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def add_saved_search(self, saved_search: SavedJobSearch) -> SavedJobSearch:
        self.session.add(saved_search)
        return saved_search

    def delete_saved_search(self, saved_search: SavedJobSearch) -> None:
        self.session.delete(saved_search)
