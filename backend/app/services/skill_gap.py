"""Deterministic, read-only skill gaps for one job and selected resume version."""

from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.repositories.skill_gap import SkillGapRepository
from backend.app.schemas.skill_gap import SkillGapAnalysisRead, SkillGapRequirementRead
from backend.app.services.candidate_profile import CandidateProfileService
from backend.app.services.fit import _education_description
from backend.app.services.job import JobService
from backend.app.services.resume_alignment import ResumeAlignmentService

_COVERED_LIMITATION = (
    "Resume evidence is a recorded reference, not a verification of proficiency or all job details."
)
_PRESENTATION_GAP_LIMITATION = (
    "Recorded candidate sources are not evidence on the selected resume version and do not establish proficiency."
)
_EVIDENCE_GAP_LIMITATION = (
    "No recorded supporting evidence is not an ability, qualification, or eligibility conclusion."
)
_EDUCATION_LIMITATION = (
    "Education requirements are not evaluated because degree and graduation vocabularies are heterogeneous."
)
_ELIGIBILITY_LIMITATION = (
    "Eligibility requirements are not evaluated because legal and policy terms require context not modeled here."
)


class SkillGapService:
    """Combines candidate-wide fit evidence with selected-version alignment evidence."""

    @staticmethod
    def analyze(job_id, resume_version_id, owner, uow) -> SkillGapAnalysisRead:
        job = JobService.get_active(job_id, uow)
        repository = SkillGapRepository(uow.session)
        version = repository.owned_version_identity(owner, resume_version_id)
        if version is None:
            raise StudentSuccessfulException(404, "RESUME_VERSION_NOT_FOUND", "Resume version not found")

        shown_by_skill = ResumeAlignmentService.selected_resume_sources(
            repository.selected_resume_skill_sources(owner, resume_version_id)
        )
        candidate_skills = CandidateProfileService._reconciled_skills(
            repository.candidate_skill_repository(), owner
        )
        candidate_by_skill = {skill.skill_id: skill for skill in candidate_skills}

        covered: list[SkillGapRequirementRead] = []
        resume_presentation_gaps: list[SkillGapRequirementRead] = []
        candidate_evidence_gaps: list[SkillGapRequirementRead] = []
        for requirement in job.skill_requirements:
            shared = {
                "category": "SKILL",
                "requirement_id": requirement.skill_id,
                "name": requirement.skill_name,
                "importance": requirement.importance,
                "description": requirement.description,
            }
            shown_sources = shown_by_skill.get(requirement.skill_id, [])
            if shown_sources:
                covered.append(
                    SkillGapRequirementRead(
                        **shared,
                        classification="COVERED",
                        explanation=(
                            "Accepted exact catalog-skill evidence is shown on this selected resume version."
                        ),
                        limitation=_COVERED_LIMITATION,
                        sources=shown_sources,
                    )
                )
                continue

            candidate_skill = candidate_by_skill.get(requirement.skill_id)
            if candidate_skill is not None:
                resume_presentation_gaps.append(
                    SkillGapRequirementRead(
                        **shared,
                        classification="RESUME_PRESENTATION_GAP",
                        explanation=(
                            "Recorded candidate evidence exists, but it is not shown on this resume."
                        ),
                        limitation=_PRESENTATION_GAP_LIMITATION,
                        sources=candidate_skill.sources,
                    )
                )
                continue

            candidate_evidence_gaps.append(
                SkillGapRequirementRead(
                    **shared,
                    classification="CANDIDATE_EVIDENCE_GAP",
                    explanation=f"No recorded supporting evidence for {requirement.skill_name}.",
                    limitation=_EVIDENCE_GAP_LIMITATION,
                )
            )

        unknown = [
            SkillGapRequirementRead(
                category="EDUCATION",
                classification="UNKNOWN_UNASSESSED",
                requirement_id=requirement.id,
                name=requirement.degree_level,
                description=_education_description(requirement),
                explanation="This education requirement is not evaluated against candidate records.",
                limitation=_EDUCATION_LIMITATION,
            )
            for requirement in job.education_requirements
        ]
        unknown.extend(
            SkillGapRequirementRead(
                category="ELIGIBILITY",
                classification="UNKNOWN_UNASSESSED",
                requirement_id=requirement.id,
                name=f"{requirement.requirement_type}: {requirement.value}",
                description=requirement.description,
                explanation="This eligibility requirement is not evaluated against candidate records.",
                limitation=_ELIGIBILITY_LIMITATION,
            )
            for requirement in job.eligibility_requirements
        )

        return SkillGapAnalysisRead(
            job_id=job.id,
            job_title=job.title,
            company_name=job.company_name,
            resume_id=version.resume_id,
            resume_title=version.resume_title,
            resume_version_id=version.resume_version_id,
            resume_version_number=version.resume_version_number,
            covered=covered,
            resume_presentation_gaps=resume_presentation_gaps,
            candidate_evidence_gaps=candidate_evidence_gaps,
            unknown=unknown,
            limitations=[
                "Analysis uses only exact canonical skill IDs linked to resume evidence, confirmed catalog skills, and project technologies.",
                "Evidence on another resume version can support recorded candidate evidence but is not shown on the selected version.",
                "Raw resume text, preferences, custom text, employment details, job titles, and name similarity are not evaluated.",
                "No recorded supporting evidence is not an ability, qualification, or eligibility conclusion.",
            ],
        )
