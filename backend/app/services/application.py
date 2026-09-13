"""Manual application tracking with one transaction per create or transition."""

from collections import defaultdict

from sqlalchemy.exc import IntegrityError

from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.models.application import (
    Application,
    ApplicationStatus,
    ApplicationStatusHistory,
)
from backend.app.models.base import utc_now
from backend.app.models.resume import Resume
from backend.app.repositories.application import ApplicationRepository
from backend.app.repositories.resume import ResumeRepository
from backend.app.schemas.application import (
    ApplicationCreate,
    ApplicationListRead,
    ApplicationRead,
    ApplicationStatusHistoryRead,
    ApplicationUpdate,
)


class ApplicationService:
    @staticmethod
    def _not_found() -> StudentSuccessfulException:
        return StudentSuccessfulException(404, "APPLICATION_NOT_FOUND", "Application not found")

    @staticmethod
    def _read_rows(repository: ApplicationRepository, rows: list) -> list[ApplicationRead]:
        ids = [row["id"] for row in rows]
        histories = defaultdict(list)
        for event in repository.histories_for(ids):
            values = dict(event)
            application_id = values.pop("application_id")
            histories[application_id].append(ApplicationStatusHistoryRead(**values))
        return [
            ApplicationRead(**dict(row), history=histories[row["id"]])
            for row in rows
        ]

    @classmethod
    def _read_one(
        cls, repository: ApplicationRepository, user_id, application_id
    ) -> ApplicationRead:
        row = repository.owned_read_row(user_id, application_id)
        if row is None:
            raise cls._not_found()
        return cls._read_rows(repository, [row])[0]

    @classmethod
    def list(cls, user_id, status: str, uow) -> ApplicationListRead:
        repository = ApplicationRepository(uow.session)
        return ApplicationListRead(items=cls._read_rows(repository, repository.list_rows(user_id, status)))

    @classmethod
    def get(cls, user_id, application_id, uow) -> ApplicationRead:
        return cls._read_one(ApplicationRepository(uow.session), user_id, application_id)

    @classmethod
    def create(cls, user_id, payload: ApplicationCreate, uow) -> ApplicationRead:
        repository = ApplicationRepository(uow.session)
        job_context = repository.job_context(payload.canonical_job_id)
        if job_context is None:
            raise StudentSuccessfulException(404, "JOB_NOT_FOUND", "Job not found")
        if repository.for_user_job_for_update(user_id, payload.canonical_job_id) is not None:
            raise StudentSuccessfulException(
                409,
                "APPLICATION_ALREADY_TRACKED",
                "This job is already in your applications",
            )

        job, company = job_context
        resume_version = None
        resume = None
        if payload.resume_version_id is not None:
            resume_repository = ResumeRepository(uow.session)
            resume_version = resume_repository.owned_version(user_id, payload.resume_version_id)
            if resume_version is None:
                raise StudentSuccessfulException(
                    404,
                    "RESUME_VERSION_NOT_FOUND",
                    "Resume version not found",
                )
            resume = uow.session.get(Resume, resume_version.resume_id)
            if resume is None:
                raise StudentSuccessfulException(
                    404,
                    "RESUME_VERSION_NOT_FOUND",
                    "Resume version not found",
                )

        application = repository.add(
            Application(
                user_id=user_id,
                job_id=job.id,
                resume_version_id=resume_version.id if resume_version is not None else None,
                resume_title_snapshot=resume.title if resume is not None else None,
                resume_hash_snapshot=(
                    resume_version.file_hash_sha256 if resume_version is not None else None
                ),
                job_title_snapshot=job.title,
                company_name_snapshot=company.name,
                current_status=ApplicationStatus.APPLIED,
                applied_at=payload.applied_at or utc_now(),
                notes=payload.notes,
            )
        )
        try:
            uow.session.flush()
        except IntegrityError as exc:
            uow.rollback()
            raise StudentSuccessfulException(
                409,
                "APPLICATION_ALREADY_TRACKED",
                "This job is already in your applications",
            ) from exc
        repository.add_history(
            ApplicationStatusHistory(
                application_id=application.id,
                previous_status=None,
                new_status=ApplicationStatus.APPLIED,
            )
        )
        uow.session.flush()
        result = cls._read_one(repository, user_id, application.id)
        uow.commit()
        return result

    @classmethod
    def update(
        cls, user_id, application_id, payload: ApplicationUpdate, uow
    ) -> ApplicationRead:
        repository = ApplicationRepository(uow.session)
        application = repository.owned_for_update(user_id, application_id)
        if application is None:
            raise cls._not_found()
        if application.version != payload.expected_version:
            raise StudentSuccessfulException(
                409,
                "APPLICATION_VERSION_CONFLICT",
                "This application changed elsewhere. Refresh and try again.",
            )

        changed = False
        if payload.status is not None and payload.status != application.current_status:
            repository.add_history(
                ApplicationStatusHistory(
                    application_id=application.id,
                    previous_status=application.current_status,
                    new_status=payload.status,
                    notes=payload.status_note,
                )
            )
            application.current_status = payload.status
            changed = True
        if "notes" in payload.model_fields_set and payload.notes != application.notes:
            application.notes = payload.notes
            changed = True

        if changed:
            application.version += 1
            application.updated_at = utc_now()
            uow.session.flush()
        result = cls._read_one(repository, user_id, application.id)
        if changed:
            uow.commit()
        return result


__all__ = ["ApplicationService"]
