"""Deterministic, evidence-preserving candidate fit analysis."""

from __future__ import annotations

from backend.app.repositories.fit import FitRepository
from backend.app.schemas.fit import FitAnalysisRead, FitRequirementRead
from backend.app.services.candidate_profile import CandidateProfileService
from backend.app.services.job import JobService

_SKILL_MATCH_LIMITATION = (
    "Recorded evidence does not establish proficiency or whether freeform job details are met."
)
_SKILL_MISSING_LIMITATION = (
    "No recorded exact catalog-skill evidence was found; this is not an ability gap."
)
_EDUCATION_LIMITATION = (
    "Education requirements are not evaluated because degree and graduation vocabularies are heterogeneous."
)
_ELIGIBILITY_LIMITATION = (
    "Eligibility requirements are not evaluated because legal and policy terms require context not modeled here."
)


class FitService:
    """Builds a derived fit read model without persisting or inferring any facts."""

    @staticmethod
    def analyze(job_id, owner, uow) -> FitAnalysisRead:
        job = JobService.get_active(job_id, uow)
        repository = FitRepository(uow.session)
        candidate_skills = CandidateProfileService._reconciled_skills(
            repository.candidate_skill_repository(), owner
        )
        skills_by_id = {skill.skill_id: skill for skill in candidate_skills}

        matched: list[FitRequirementRead] = []
        missing: list[FitRequirementRead] = []
        for requirement in job.skill_requirements:
            candidate_skill = skills_by_id.get(requirement.skill_id)
            shared = {
                "category": "SKILL",
                "requirement_id": requirement.skill_id,
                "name": requirement.skill_name,
                "importance": requirement.importance,
                "description": requirement.description,
            }
            if candidate_skill is None:
                missing.append(
                    FitRequirementRead(
                        **shared,
                        explanation="No exact catalog skill reference is recorded in the candidate profile.",
                        limitation=_SKILL_MISSING_LIMITATION,
                    )
                )
            else:
                matched.append(
                    FitRequirementRead(
                        **shared,
                        explanation="An exact catalog skill reference is recorded in the candidate profile.",
                        limitation=_SKILL_MATCH_LIMITATION,
                        sources=candidate_skill.sources,
                    )
                )

        unknown = [
            FitRequirementRead(
                category="EDUCATION",
                requirement_id=requirement.id,
                name=requirement.degree_level,
                description=_education_description(requirement),
                explanation="This education requirement is not evaluated against candidate records.",
                limitation=_EDUCATION_LIMITATION,
            )
            for requirement in job.education_requirements
        ]
        unknown.extend(
            FitRequirementRead(
                category="ELIGIBILITY",
                requirement_id=requirement.id,
                name=f"{requirement.requirement_type}: {requirement.value}",
                description=requirement.description,
                explanation="This eligibility requirement is not evaluated against candidate records.",
                limitation=_ELIGIBILITY_LIMITATION,
            )
            for requirement in job.eligibility_requirements
        )

        return FitAnalysisRead(
            job_id=job.id,
            job_title=job.title,
            company_name=job.company_name,
            matched=matched,
            missing=missing,
            unknown=unknown,
            limitations=[
                "Skill matching uses only exact canonical skill IDs; custom skill text and name similarity are not evaluated.",
                "No recorded evidence is not an ability, qualification, or eligibility conclusion.",
                "Resume evidence includes all stored versions and may be historical, nonprimary, or retained after a reparse failure.",
                "Education and eligibility requirements are shown as unknown because their vocabularies and legal terms are not evaluated.",
            ],
        )


def _education_description(requirement) -> str | None:
    if requirement.target_grad_start is None and requirement.target_grad_end is None:
        return None
    if requirement.target_grad_start is not None and requirement.target_grad_end is not None:
        return (
            "Target graduation period: "
            f"{requirement.target_grad_start.isoformat()} to {requirement.target_grad_end.isoformat()}"
        )
    if requirement.target_grad_start is not None:
        return f"Target graduation begins: {requirement.target_grad_start.isoformat()}"
    return f"Target graduation ends: {requirement.target_grad_end.isoformat()}"
