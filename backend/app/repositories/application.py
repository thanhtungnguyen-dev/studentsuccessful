"""Owner-scoped application reads and persistence without transaction ownership."""

from uuid import UUID

from sqlalchemy import func, select

from backend.app.models.application import Application, ApplicationStatusHistory
from backend.app.models.job import NormalizedJob
from backend.app.models.resume import Resume, ResumeVersion
from backend.app.models.taxonomy import Company


class ApplicationRepository:
    def __init__(self, session):
        self.session = session

    @staticmethod
    def _read_statement(user_id: UUID):
        return (
            select(
                Application.id,
                Application.job_id.label("canonical_job_id"),
                func.coalesce(Application.job_title_snapshot, NormalizedJob.title).label("job_title"),
                func.coalesce(Application.company_name_snapshot, Company.name).label("company_name"),
                NormalizedJob.application_url,
                NormalizedJob.lifecycle.label("job_lifecycle"),
                Application.current_status,
                Application.resume_version_id,
                func.coalesce(Application.resume_title_snapshot, Resume.title).label("resume_title"),
                ResumeVersion.version_number.label("resume_version_number"),
                Application.applied_at,
                Application.notes,
                Application.version,
                Application.created_at,
                Application.updated_at,
            )
            .select_from(Application)
            .outerjoin(NormalizedJob, NormalizedJob.id == Application.job_id)
            .outerjoin(Company, Company.id == NormalizedJob.company_id)
            .outerjoin(ResumeVersion, ResumeVersion.id == Application.resume_version_id)
            .outerjoin(Resume, Resume.id == ResumeVersion.resume_id)
            .where(Application.user_id == user_id)
        )

    def list_rows(self, user_id: UUID, status: str) -> list:
        statement = self._read_statement(user_id)
        if status != "ALL":
            statement = statement.where(Application.current_status == status)
        return list(
            self.session.execute(
                statement.order_by(Application.updated_at.desc(), Application.id.desc())
            ).mappings()
        )

    def owned_read_row(self, user_id: UUID, application_id: UUID):
        return self.session.execute(
            self._read_statement(user_id).where(Application.id == application_id)
        ).mappings().one_or_none()

    def histories_for(self, application_ids: list[UUID]) -> list:
        if not application_ids:
            return []
        return list(
            self.session.execute(
                select(
                    ApplicationStatusHistory.id,
                    ApplicationStatusHistory.application_id,
                    ApplicationStatusHistory.previous_status,
                    ApplicationStatusHistory.new_status,
                    ApplicationStatusHistory.notes,
                    ApplicationStatusHistory.transitioned_at,
                )
                .where(ApplicationStatusHistory.application_id.in_(application_ids))
                .order_by(
                    ApplicationStatusHistory.application_id,
                    ApplicationStatusHistory.transitioned_at,
                    ApplicationStatusHistory.id,
                )
            ).mappings()
        )

    def owned_for_update(self, user_id: UUID, application_id: UUID) -> Application | None:
        return self.session.scalar(
            select(Application)
            .where(Application.user_id == user_id, Application.id == application_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def for_user_job_for_update(self, user_id: UUID, job_id: UUID) -> Application | None:
        return self.session.scalar(
            select(Application)
            .where(Application.user_id == user_id, Application.job_id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def job_context(self, job_id: UUID):
        return self.session.execute(
            select(NormalizedJob, Company)
            .join(Company, Company.id == NormalizedJob.company_id)
            .where(NormalizedJob.id == job_id)
        ).one_or_none()

    def add(self, application: Application) -> Application:
        self.session.add(application)
        return application

    def add_history(self, event: ApplicationStatusHistory) -> ApplicationStatusHistory:
        self.session.add(event)
        return event


__all__ = ["ApplicationRepository"]
