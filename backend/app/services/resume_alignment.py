"""Deterministic ResumeVersion-to-job alignment without persistence or inference."""

from __future__ import annotations

from collections import defaultdict

from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.repositories.resume_alignment import ResumeAlignmentRepository
from backend.app.schemas.candidate_profile import CandidateSkillSourceRead
from backend.app.schemas.resume_alignment import (
    ResumeAlignmentRead,
    ResumeAlignmentRequirementRead,
)
from backend.app.services.fit import _education_description
from backend.app.services.job import JobService

_SHOWN_LIMITATION = (
    "Resume evidence is a recorded reference, not a verification of proficiency or all job details."
)
_CANDIDATE_EVIDENCE_LIMITATION = (
    "These sources are not evidence on the selected resume version and do not establish proficiency."
)
_NO_EVIDENCE_LIMITATION = (
    "No recorded evidence is not an ability, qualification, or eligibility conclusion."
)
_EDUCATION_LIMITATION = (
    "Education requirements are not evaluated because degree and graduation vocabularies are heterogeneous."
)
_ELIGIBILITY_LIMITATION = (
    "Eligibility requirements are not evaluated because legal and policy terms require context not modeled here."
)


class ResumeAlignmentService:
    """Build an exact-version, exact-catalog-skill read model without mutations."""

    @staticmethod
    def analyze(job_id, resume_version_id, owner, uow) -> ResumeAlignmentRead:
        job = JobService.get_active(job_id, uow)
        repository = ResumeAlignmentRepository(uow.session)
        version = repository.owned_version_identity(owner, resume_version_id)
        if version is None:
            raise StudentSuccessfulException(404, "RESUME_VERSION_NOT_FOUND", "Resume version not found")

        shown_by_skill = ResumeAlignmentService.selected_resume_sources(
            repository.selected_resume_skill_sources(owner, resume_version_id)
        )
        candidate_sources_by_skill = ResumeAlignmentService._candidate_non_resume_sources(
            repository, owner
        )

        shown_on_resume: list[ResumeAlignmentRequirementRead] = []
        candidate_evidence_not_shown: list[ResumeAlignmentRequirementRead] = []
        no_recorded_evidence: list[ResumeAlignmentRequirementRead] = []
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
                shown_on_resume.append(
                    ResumeAlignmentRequirementRead(
                        **shared,
                        explanation=(
                            "Accepted exact catalog-skill evidence is shown on this selected resume version."
                        ),
                        limitation=_SHOWN_LIMITATION,
                        sources=shown_sources,
                    )
                )
                continue
            candidate_sources = candidate_sources_by_skill.get(requirement.skill_id, [])
            if candidate_sources:
                candidate_evidence_not_shown.append(
                    ResumeAlignmentRequirementRead(
                        **shared,
                        explanation=(
                            "Recorded candidate evidence exists, but it is not shown in this resume version."
                        ),
                        limitation=_CANDIDATE_EVIDENCE_LIMITATION,
                        sources=candidate_sources,
                    )
                )
                continue
            no_recorded_evidence.append(
                ResumeAlignmentRequirementRead(
                    **shared,
                    explanation=(
                        "No accepted exact catalog-skill evidence is recorded on this resume version "
                        "or in confirmed skills and project technologies."
                    ),
                    limitation=_NO_EVIDENCE_LIMITATION,
                )
            )

        unknown_unassessed = [
            ResumeAlignmentRequirementRead(
                category="EDUCATION",
                requirement_id=requirement.id,
                name=requirement.degree_level,
                description=_education_description(requirement),
                explanation="This education requirement is not evaluated against candidate records.",
                limitation=_EDUCATION_LIMITATION,
            )
            for requirement in job.education_requirements
        ]
        unknown_unassessed.extend(
            ResumeAlignmentRequirementRead(
                category="ELIGIBILITY",
                requirement_id=requirement.id,
                name=f"{requirement.requirement_type}: {requirement.value}",
                description=requirement.description,
                explanation="This eligibility requirement is not evaluated against candidate records.",
                limitation=_ELIGIBILITY_LIMITATION,
            )
            for requirement in job.eligibility_requirements
        )

        return ResumeAlignmentRead(
            job_id=job.id,
            job_title=job.title,
            company_name=job.company_name,
            resume_id=version.resume_id,
            resume_title=version.resume_title,
            resume_version_id=version.resume_version_id,
            resume_version_number=version.resume_version_number,
            shown_on_resume=shown_on_resume,
            candidate_evidence_not_shown=candidate_evidence_not_shown,
            no_recorded_evidence=no_recorded_evidence,
            unknown_unassessed=unknown_unassessed,
            limitations=[
                "Alignment uses only exact canonical skill IDs linked to the selected resume version, confirmed catalog skills, and project technologies.",
                "Evidence on another resume version never counts as shown on this selected version.",
                "Raw resume text, preferences, custom text, employment details, job titles, and name similarity are not evaluated.",
                "No recorded evidence is not an ability, qualification, or eligibility conclusion.",
            ],
        )

    @staticmethod
    def selected_resume_sources(rows) -> dict[object, list[CandidateSkillSourceRead]]:
        sources: dict[object, list[CandidateSkillSourceRead]] = defaultdict(list)
        for (
            skill_id,
            _name,
            _category,
            resume_id,
            resume_title,
            version_id,
            version_number,
            evidence_id,
            ordinal,
            evidence_category,
            section_header,
            confidence,
        ) in rows:
            sources[skill_id].append(
                CandidateSkillSourceRead(
                    source_type="RESUME_EVIDENCE",
                    source_id=evidence_id,
                    resume_id=resume_id,
                    resume_title=resume_title,
                    resume_version_id=version_id,
                    resume_version_number=version_number,
                    evidence_ordinal=ordinal,
                    evidence_category=evidence_category,
                    evidence_section_header=section_header,
                    parser_confidence=confidence,
                )
            )
        return sources

    @staticmethod
    def _candidate_non_resume_sources(repository, owner) -> dict[object, list[CandidateSkillSourceRead]]:
        sources: dict[object, list[CandidateSkillSourceRead]] = defaultdict(list)
        for user_skill_id, skill_id, _name, _category in repository.confirmed_catalog_skills(owner):
            sources[skill_id].append(
                CandidateSkillSourceRead(
                    source_type="CONFIRMED_BY_USER", source_id=user_skill_id
                )
            )
        for skill_id, _name, _category, project_id, project_title in repository.project_catalog_skills(owner):
            sources[skill_id].append(
                CandidateSkillSourceRead(
                    source_type="PROJECT",
                    source_id=project_id,
                    project_id=project_id,
                    project_title=project_title,
                )
            )
        for source_rows in sources.values():
            source_rows.sort(
                key=lambda source: (
                    0 if source.source_type == "CONFIRMED_BY_USER" else 1,
                    source.project_title.casefold() if source.project_title else "",
                    str(source.source_id),
                )
            )
        return sources
