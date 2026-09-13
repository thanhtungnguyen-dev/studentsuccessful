"""Deterministic, read-only candidate-profile aggregation."""

from collections import defaultdict

from backend.app.repositories.candidate_profile import CandidateProfileRepository
from backend.app.schemas.candidate_profile import (
    CandidateCustomSkillRead,
    CandidateCustomSkillSourceRead,
    CandidateProfileRead,
    CandidateResumeEvidenceRead,
    CandidateResumeEvidenceSkillRead,
    CandidateSkillRead,
    CandidateSkillSourceRead,
)
from backend.app.schemas.education import EducationRead
from backend.app.schemas.employment import EmploymentRead
from backend.app.schemas.profile import ProfileRead
from backend.app.schemas.work_authorization import WorkAuthorizationRead


class CandidateProfileService:
    """Combines owned source records without persistence, inference, or matching."""

    @staticmethod
    def read(owner, uow) -> CandidateProfileRead:
        repository = CandidateProfileRepository(uow.session)
        profile = repository.profile_for_owner(owner)
        return CandidateProfileRead(
            profile=ProfileRead.model_validate(profile) if profile is not None else None,
            education=[EducationRead.model_validate(row) for row in repository.education_for_owner(owner)],
            employment=[EmploymentRead.model_validate(row) for row in repository.employment_for_owner(owner)],
            work_authorizations=[
                WorkAuthorizationRead.model_validate(row)
                for row in repository.work_authorizations_for_owner(owner)
            ],
            preferences=repository.preferences_for_owner(owner),
            projects=repository.projects_for_owner(owner),
            skills=CandidateProfileService._reconciled_skills(repository, owner),
            custom_skills=CandidateProfileService._custom_skills(repository, owner),
            resume_evidence=CandidateProfileService._resume_evidence(repository, owner),
        )

    @staticmethod
    def _reconciled_skills(repository, owner) -> list[CandidateSkillRead]:
        skills: dict[object, dict] = {}

        def add(skill_id, name, category, source):
            bucket = skills.setdefault(
                skill_id,
                {"skill_id": skill_id, "name": name, "category": category, "sources": []},
            )
            bucket["sources"].append(source)

        for user_skill_id, skill_id, name, category in repository.confirmed_catalog_skills(owner):
            add(
                skill_id,
                name,
                category,
                CandidateSkillSourceRead(
                    source_type="CONFIRMED_BY_USER", source_id=user_skill_id
                ),
            )
        for (
            skill_id,
            name,
            category,
            resume_id,
            resume_title,
            version_id,
            version_number,
            evidence_id,
            ordinal,
            evidence_category,
            section_header,
            confidence,
        ) in repository.resume_skill_sources(owner):
            add(
                skill_id,
                name,
                category,
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
                ),
            )
        for skill_id, name, category, project_id, project_title in repository.project_catalog_skills(owner):
            add(
                skill_id,
                name,
                category,
                CandidateSkillSourceRead(
                    source_type="PROJECT",
                    source_id=project_id,
                    project_id=project_id,
                    project_title=project_title,
                ),
            )

        source_order = {"CONFIRMED_BY_USER": 0, "RESUME_EVIDENCE": 1, "PROJECT": 2}
        for row in skills.values():
            row["sources"].sort(
                key=lambda source: (
                    source_order[source.source_type],
                    source.resume_title.casefold() if source.resume_title else "",
                    source.resume_version_number or 0,
                    source.evidence_ordinal if source.evidence_ordinal is not None else -1,
                    source.project_title.casefold() if source.project_title else "",
                    str(source.source_id),
                )
            )
        return [
            CandidateSkillRead(**row)
            for row in sorted(
                skills.values(), key=lambda row: (row["name"].casefold(), str(row["skill_id"]))
            )
        ]

    @staticmethod
    def _resume_evidence(repository, owner) -> list[CandidateResumeEvidenceRead]:
        skills_by_evidence_id: dict[object, list[CandidateResumeEvidenceSkillRead]] = defaultdict(list)
        for evidence_id, skill_id, name, confidence in repository.evidence_recognized_skills_for_owner(owner):
            skills_by_evidence_id[evidence_id].append(
                CandidateResumeEvidenceSkillRead(
                    skill_id=skill_id, name=name, parser_confidence=confidence
                )
            )
        return [
            CandidateResumeEvidenceRead(
                resume_id=resume_id,
                resume_title=resume_title,
                resume_version_id=version_id,
                resume_version_number=version_number,
                evidence_item_id=evidence_id,
                ordinal=ordinal,
                category=category,
                section_header=section_header,
                bullet_text=bullet_text,
                recognized_skills=skills_by_evidence_id[evidence_id],
            )
            for (
                resume_id,
                resume_title,
                version_id,
                version_number,
                evidence_id,
                ordinal,
                category,
                section_header,
                bullet_text,
            ) in repository.evidence_for_owner(owner)
        ]

    @staticmethod
    def _custom_skills(repository, owner) -> list[CandidateCustomSkillRead]:
        confirmed, project = repository.custom_skill_sources(owner)
        grouped: dict[str, dict] = {}
        for source_id, value, normalized_value in confirmed:
            bucket = grouped.setdefault(normalized_value, {"name": value, "sources": []})
            bucket["sources"].append(
                CandidateCustomSkillSourceRead(
                    source_type="CONFIRMED_BY_USER", source_id=source_id
                )
            )
        for source_id, value, normalized_value, project_id, project_title in project:
            bucket = grouped.setdefault(normalized_value, {"name": value, "sources": []})
            bucket["sources"].append(
                CandidateCustomSkillSourceRead(
                    source_type="PROJECT",
                    source_id=source_id,
                    project_id=project_id,
                    project_title=project_title,
                )
            )
        for row in grouped.values():
            row["sources"].sort(
                key=lambda source: (
                    0 if source.source_type == "CONFIRMED_BY_USER" else 1,
                    source.project_title.casefold() if source.project_title else "",
                    str(source.source_id),
                )
            )
        return [
            CandidateCustomSkillRead(**row)
            for _, row in sorted(grouped.items(), key=lambda item: item[0])
        ]
