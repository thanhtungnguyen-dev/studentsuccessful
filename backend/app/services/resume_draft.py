"""Deterministic, evidence-grounded resume drafting derived from Phase 15 actions."""

from backend.app.schemas.candidate_profile import CandidateSkillSourceRead
from backend.app.schemas.resume_draft import ResumeDraftItemRead, ResumeTailoringDraftRead
from backend.app.schemas.resume_plan import ResumeImprovementActionRead
from backend.app.services.resume_plan import ResumeImprovementPlanService


class ResumeTailoringDraftService:
    """Creates non-persistent draft fragments without rematching or inspecting free text."""

    @staticmethod
    def _item(
        action: ResumeImprovementActionRead,
        *,
        sources: list[CandidateSkillSourceRead] | None = None,
        reason: str | None = None,
        limitation: str | None = None,
        draft_text: str | None = None,
    ) -> ResumeDraftItemRead:
        return ResumeDraftItemRead(
            category=action.category,
            action=action.action,
            requirement_id=action.requirement_id,
            name=action.name,
            importance=action.importance,
            description=action.description,
            reason=reason if reason is not None else action.reason,
            limitation=limitation if limitation is not None else action.limitation,
            sources=list(action.sources if sources is None else sources),
            draft_text=draft_text,
        )

    @staticmethod
    def _eligible_sources(
        action: ResumeImprovementActionRead, selected_resume_version_id
    ) -> list[CandidateSkillSourceRead]:
        """Accept only structured candidate sources in the selected-version scope."""

        return [
            source
            for source in action.sources
            if source.source_type in {"CONFIRMED_BY_USER", "PROJECT"}
            or (
                source.source_type == "RESUME_EVIDENCE"
                and source.resume_version_id == selected_resume_version_id
            )
        ]

    @staticmethod
    def _draft_text(action: ResumeImprovementActionRead, source: CandidateSkillSourceRead) -> str:
        """Return only a source label and exact catalog-skill name, never inferred prose."""

        if source.source_type == "PROJECT" and source.project_title:
            return f"{source.project_title} — {action.name}."
        return f"{action.name}."

    @classmethod
    def analyze(cls, job_id, resume_version_id, owner, uow) -> ResumeTailoringDraftRead:
        """Map Phase 15 safe actions to controlled draft fragments without any writes."""

        plan = ResumeImprovementPlanService.analyze(job_id, resume_version_id, owner, uow)

        keep = [
            cls._item(
                action,
                sources=[
                    source
                    for source in action.sources
                    if source.source_type != "RESUME_EVIDENCE"
                    or source.resume_version_id == plan.resume_version_id
                ],
            )
            for action in plan.keep
        ]

        draft_suggestions: list[ResumeDraftItemRead] = []
        unavailable_presentation_evidence: list[ResumeDraftItemRead] = []
        for action in plan.consider_adding_existing_evidence:
            eligible_sources = cls._eligible_sources(action, plan.resume_version_id)
            if not eligible_sources:
                unavailable_presentation_evidence.append(
                    cls._item(
                        action,
                        sources=[],
                        reason=(
                            "No selected-resume, confirmed-skill, or recorded project-technology "
                            f"evidence supports generating a draft statement for {action.name}."
                        ),
                        limitation=(
                            "Evidence on another resume version is not used as evidence for this "
                            "selected resume version."
                        ),
                    )
                )
                continue
            for source in eligible_sources:
                draft_suggestions.append(
                    cls._item(
                        action,
                        sources=[source],
                        reason=(
                            "This draft fragment uses only the cited recorded candidate source "
                            "and exact requirement name."
                        ),
                        limitation=(
                            "Review the wording before use; it is a draft fragment, not a new "
                            "candidate fact or resume change."
                        ),
                        draft_text=cls._draft_text(action, source),
                    )
                )

        unsupported = unavailable_presentation_evidence + [
            cls._item(action, sources=[])
            for action in plan.do_not_claim_without_evidence
        ]
        manual_review = [cls._item(action, sources=[]) for action in plan.manual_review]

        return ResumeTailoringDraftRead(
            job_id=plan.job_id,
            job_title=plan.job_title,
            company_name=plan.company_name,
            resume_id=plan.resume_id,
            resume_title=plan.resume_title,
            resume_version_id=plan.resume_version_id,
            resume_version_number=plan.resume_version_number,
            keep=keep,
            draft_suggestions=draft_suggestions,
            unsupported=unsupported,
            manual_review=manual_review,
            limitations=[
                "Draft text is derived only from the cited exact candidate-owned source and is never persisted.",
                "Raw resume text, preference records, free-text descriptions, and job requirements do not create draft facts.",
                "Evidence on another ResumeVersion does not support draft text for the selected ResumeVersion.",
            ],
        )
