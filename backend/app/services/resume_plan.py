"""Conservative, read-only resume actions derived from deterministic skill gaps."""

from backend.app.schemas.resume_plan import (
    ResumeImprovementActionRead,
    ResumeImprovementPlanRead,
)
from backend.app.services.skill_gap import SkillGapService


class ResumeImprovementPlanService:
    """Maps Phase 14 outcomes to actions without rematching or writing resume content."""

    @staticmethod
    def analyze(job_id, resume_version_id, owner, uow) -> ResumeImprovementPlanRead:
        gaps = SkillGapService.analyze(job_id, resume_version_id, owner, uow)

        keep = [
            ResumeImprovementActionRead(
                category=requirement.category,
                action="KEEP",
                requirement_id=requirement.requirement_id,
                name=requirement.name,
                importance=requirement.importance,
                description=requirement.description,
                reason=(
                    "Accepted exact catalog-skill evidence is already shown on this selected "
                    "resume version. No change is required."
                ),
                limitation=requirement.limitation,
                sources=requirement.sources,
            )
            for requirement in gaps.covered
        ]
        consider_adding_existing_evidence = [
            ResumeImprovementActionRead(
                category=requirement.category,
                action="CONSIDER_ADDING_EXISTING_EVIDENCE",
                requirement_id=requirement.requirement_id,
                name=requirement.name,
                importance=requirement.importance,
                description=requirement.description,
                reason=(
                    f"Recorded {requirement.name} evidence exists but is not shown on "
                    f"ResumeVersion {gaps.resume_version_number}."
                ),
                limitation=requirement.limitation,
                sources=requirement.sources,
            )
            for requirement in gaps.resume_presentation_gaps
        ]
        do_not_claim_without_evidence = [
            ResumeImprovementActionRead(
                category=requirement.category,
                action="DO_NOT_CLAIM_WITHOUT_EVIDENCE",
                requirement_id=requirement.requirement_id,
                name=requirement.name,
                importance=requirement.importance,
                description=requirement.description,
                reason=(
                    f"No recorded supporting evidence supports adding {requirement.name} "
                    "to this resume."
                ),
                limitation=requirement.limitation,
            )
            for requirement in gaps.candidate_evidence_gaps
        ]
        manual_review = [
            ResumeImprovementActionRead(
                category=requirement.category,
                action="MANUAL_REVIEW",
                requirement_id=requirement.requirement_id,
                name=requirement.name,
                importance=requirement.importance,
                description=requirement.description,
                reason=f"{requirement.explanation} Manual review is needed.",
                limitation=requirement.limitation,
            )
            for requirement in gaps.unknown
        ]

        return ResumeImprovementPlanRead(
            job_id=gaps.job_id,
            job_title=gaps.job_title,
            company_name=gaps.company_name,
            resume_id=gaps.resume_id,
            resume_title=gaps.resume_title,
            resume_version_id=gaps.resume_version_id,
            resume_version_number=gaps.resume_version_number,
            keep=keep,
            consider_adding_existing_evidence=consider_adding_existing_evidence,
            do_not_claim_without_evidence=do_not_claim_without_evidence,
            manual_review=manual_review,
            limitations=[
                "Actions are derived only from exact recorded evidence and do not generate resume text.",
                "Evidence on another resume version can support an action but is not shown on the selected version.",
                "No recorded supporting evidence is not an ability, qualification, or eligibility conclusion.",
            ],
        )
