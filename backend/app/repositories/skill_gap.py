"""Read-only source boundary for deterministic skill gap analysis."""

from backend.app.repositories.candidate_profile import CandidateProfileRepository
from backend.app.repositories.resume_alignment import ResumeAlignmentRepository


class SkillGapRepository:
    """Reuses owner-scoped candidate and selected-version evidence queries."""

    def __init__(self, session):
        self._alignment = ResumeAlignmentRepository(session)
        self._candidate_profile = CandidateProfileRepository(session)

    def owned_version_identity(self, owner, version_id):
        return self._alignment.owned_version_identity(owner, version_id)

    def selected_resume_skill_sources(self, owner, version_id):
        return self._alignment.selected_resume_skill_sources(owner, version_id)

    def candidate_skill_repository(self) -> CandidateProfileRepository:
        return self._candidate_profile
