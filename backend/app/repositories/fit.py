"""Read-only data access for the isolated candidate-fit read model."""

from backend.app.repositories.candidate_profile import CandidateProfileRepository


class FitRepository:
    """Owns fit's candidate lookup boundary while reusing proven owner scoping."""

    def __init__(self, session):
        self.session = session
        self._candidate_profile = CandidateProfileRepository(session)

    def candidate_skill_repository(self) -> CandidateProfileRepository:
        """Return the owner-scoped source repository used for exact skill evidence."""

        return self._candidate_profile
