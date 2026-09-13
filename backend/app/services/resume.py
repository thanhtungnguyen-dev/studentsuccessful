"""Managed resume families, immutable uploads, and deterministic derived evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
from uuid import UUID, uuid4
from zipfile import BadZipFile, ZipFile

from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.core.storage import StorageAdapter, get_storage_adapter
from backend.app.models.resume import Resume, ResumeEvidenceItem, ResumeEvidenceSkill, ResumeVersion
from backend.app.parsers.resume import MAX_EXTRACTED_TEXT_CHARS, ParsedResume, ResumeParser
from backend.app.repositories.resume import ResumeRepository
from backend.app.schemas.resume import (
    ResumeCreate,
    ResumeEvidenceItemRead,
    ResumeEvidenceSkillRead,
    ResumeExtractedTextRead,
    ResumePrimaryVersionUpdate,
    ResumeRead,
    ResumeUpdate,
    ResumeVersionRead,
)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_DOCX_ENTRIES = 2_000
MAX_DOCX_EXPANDED_BYTES = 25 * 1024 * 1024
MAX_DOCX_COMPRESSION_RATIO = 100
EVIDENCE_CATEGORIES = frozenset({"EDUCATION", "EXPERIENCE", "PROJECTS", "SKILLS", "OTHER"})
_SKILL_TERM_EDGE = r"[\w.+#/-]"


@dataclass(frozen=True)
class ValidatedResumeUpload:
    filename: str
    file_format: str
    content: bytes
    sha256_hex: str


def _not_found() -> StudentSuccessfulException:
    return StudentSuccessfulException(404, "RESUME_NOT_FOUND", "Resume not found")


def _version_not_found() -> StudentSuccessfulException:
    return StudentSuccessfulException(404, "RESUME_VERSION_NOT_FOUND", "Resume version not found")


def _invalid_upload(detail: str) -> StudentSuccessfulException:
    return StudentSuccessfulException(422, "INVALID_RESUME_UPLOAD", detail)


class ResumeService:
    """Own resume families, immutable uploads, and derived parser evidence transactions."""

    storage_factory = staticmethod(get_storage_adapter)

    @staticmethod
    def validate_upload(
        filename: str | None, content: bytes, declared_content_type: str | None = None
    ) -> ValidatedResumeUpload:
        if not filename or not isinstance(filename, str):
            raise _invalid_upload("Choose a PDF or DOCX file")
        normalized_name = filename.strip()
        if (
            not normalized_name
            or "\x00" in normalized_name
            or "/" in normalized_name
            or "\\" in normalized_name
            or PurePosixPath(normalized_name).name != normalized_name
        ):
            raise _invalid_upload("Invalid upload filename")
        if not content:
            raise _invalid_upload("Uploaded file is empty")
        if len(content) > MAX_UPLOAD_BYTES:
            raise _invalid_upload("Resume files must be 5 MB or smaller")

        extension = PurePosixPath(normalized_name).suffix.lower()
        if extension == ".pdf":
            ResumeService._validate_pdf(content)
            file_format = "PDF"
            allowed_content_types = {"", "application/pdf", "application/octet-stream"}
        elif extension == ".docx":
            ResumeService._validate_docx(content)
            file_format = "DOCX"
            allowed_content_types = {
                "",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/octet-stream",
            }
        else:
            raise _invalid_upload("Only PDF and DOCX files are accepted")
        if (declared_content_type or "").lower().strip() not in allowed_content_types:
            raise _invalid_upload("The declared file type does not match the selected document")
        return ValidatedResumeUpload(
            filename=normalized_name,
            file_format=file_format,
            content=content,
            sha256_hex=sha256(content).hexdigest(),
        )

    @staticmethod
    def _validate_pdf(content: bytes) -> None:
        # This is format validation, not PDF parsing or text extraction.
        if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-2048:]:
            raise _invalid_upload("The selected .pdf file is not a valid PDF document")

    @staticmethod
    def _validate_docx(content: bytes) -> None:
        # Inspect the ZIP directory only. Never extract untrusted entries to disk.
        try:
            with ZipFile(BytesIO(content)) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_DOCX_ENTRIES:
                    raise _invalid_upload("The DOCX archive contains too many entries")
                names = {entry.filename for entry in entries}
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise _invalid_upload("The selected .docx file is not an Office document")
                expanded = 0
                for entry in entries:
                    entry_path = PurePosixPath(entry.filename)
                    if (
                        not entry.filename
                        or "\\" in entry.filename
                        or entry_path.is_absolute()
                        or any(part in {"", ".", ".."} for part in entry_path.parts)
                    ):
                        raise _invalid_upload("The DOCX archive contains an unsafe entry name")
                    if entry.flag_bits & 0x1:
                        raise _invalid_upload("Encrypted DOCX files are not supported")
                    if entry.file_size < 0 or entry.file_size > MAX_DOCX_EXPANDED_BYTES:
                        raise _invalid_upload("The DOCX archive expands beyond the safe limit")
                    expanded += entry.file_size
                    if expanded > MAX_DOCX_EXPANDED_BYTES:
                        raise _invalid_upload("The DOCX archive expands beyond the safe limit")
                    if entry.file_size and not entry.compress_size:
                        raise _invalid_upload("The DOCX archive has an unsafe compression ratio")
                    if entry.compress_size and entry.file_size / entry.compress_size > MAX_DOCX_COMPRESSION_RATIO:
                        raise _invalid_upload("The DOCX archive has an unsafe compression ratio")
        except StudentSuccessfulException:
            raise
        except (BadZipFile, OSError, ValueError) as error:
            raise _invalid_upload("The selected .docx file is not a valid Office document") from error

    @staticmethod
    def list(owner: UUID, uow) -> list[ResumeRead]:
        return [ResumeRead.model_validate(row) for row in ResumeRepository(uow.session).list_for_owner(owner)]

    @staticmethod
    def get(owner: UUID, resume_id: UUID, uow) -> ResumeRead:
        row = ResumeRepository(uow.session).owned_resume(owner, resume_id)
        if row is None:
            raise _not_found()
        return ResumeRead.model_validate(row)

    @staticmethod
    def create(owner: UUID, payload: ResumeCreate, uow) -> ResumeRead:
        row = Resume(user_id=owner, **payload.model_dump())
        uow.session.add(row)
        uow.session.flush()
        result = ResumeRead.model_validate(row)
        uow.commit()
        return result

    @staticmethod
    def update(owner: UUID, resume_id: UUID, payload: ResumeUpdate, uow) -> ResumeRead:
        repository = ResumeRepository(uow.session)
        row = repository.owned_resume(owner, resume_id, lock=True)
        if row is None:
            raise _not_found()
        changes = payload.model_dump(exclude_unset=True)
        if "title" in changes:
            row.title = changes["title"]
        uow.session.flush()
        result = ResumeRead.model_validate(row)
        uow.commit()
        return result

    @classmethod
    def upload_version(
        cls,
        owner: UUID,
        resume_id: UUID,
        filename: str | None,
        content: bytes,
        declared_content_type: str | None,
        uow,
    ) -> ResumeVersionRead:
        upload = cls.validate_upload(filename, content, declared_content_type)
        repository = ResumeRepository(uow.session)
        resume = repository.owned_resume(owner, resume_id, lock=True)
        if resume is None:
            raise _not_found()
        version_id = uuid4()
        version_number = repository.next_version_number(resume.id)
        extension = "pdf" if upload.file_format == "PDF" else "docx"
        storage_key = f"resumes/{owner.hex}/{resume.id.hex}/{version_id.hex}.{extension}"
        version = ResumeVersion(
            id=version_id,
            resume_id=resume.id,
            version_number=version_number,
            storage_key=storage_key,
            file_format=upload.file_format,
            file_size_bytes=len(upload.content),
            file_hash_sha256=upload.sha256_hex,
            is_primary_active=not repository.has_versions(resume.id),
            parse_status="PENDING",
            raw_extracted_text=None,
        )
        storage: StorageAdapter = cls.storage_factory()
        try:
            storage.save(storage_key, upload.content)
            uow.session.add(version)
            uow.session.flush()
            result = ResumeVersionRead.model_validate(version)
            uow.commit()
            return result
        except Exception:
            # A storage backend may partially write before raising. The key is a fresh
            # server-generated UUID, so a best-effort delete is safe in either case.
            cls._delete_quietly(storage, storage_key)
            raise

    @staticmethod
    def list_versions(owner: UUID, resume_id: UUID, uow) -> list[ResumeVersionRead]:
        repository = ResumeRepository(uow.session)
        if repository.owned_resume(owner, resume_id) is None:
            raise _not_found()
        return [
            ResumeVersionRead.model_validate(row)
            for row in repository.versions_for_resume(resume_id)
        ]

    @staticmethod
    def get_version(owner: UUID, version_id: UUID, uow) -> ResumeVersionRead:
        version = ResumeRepository(uow.session).owned_version(owner, version_id)
        if version is None:
            raise _version_not_found()
        return ResumeVersionRead.model_validate(version)

    @classmethod
    def parse_version(cls, owner: UUID, version_id: UUID, uow) -> ResumeVersionRead:
        """Derive evidence for one owned version without changing its uploaded identity.

        A row lock serializes parse/reparse requests for this exact version.  The
        parser runs locally and entirely in memory; it can update only derived
        operational fields and evidence rows for that version.
        """
        repository = ResumeRepository(uow.session)
        version = repository.owned_version(owner, version_id, lock=True)
        if version is None:
            raise _version_not_found()

        try:
            content = cls.storage_factory().open(version.storage_key)
        except (FileNotFoundError, OSError, ValueError) as error:
            # A missing/invalid managed object is deliberately indistinguishable
            # from an unknown version.  Persist a retryable operational failure
            # for its owner without disclosing a storage path or parser detail.
            cls._mark_parse_failed(version, uow)
            raise _version_not_found() from error

        try:
            parsed = ResumeParser.parse(content, version.file_format)
            evidence_items = cls._validated_evidence_items(version.id, parsed)
        except Exception:
            # Parser implementations and document libraries are untrusted at this
            # boundary.  Keep the previous successful raw text/evidence untouched
            # and return the existing safe status vocabulary for a retry.
            return cls._mark_parse_failed(version, uow)

        # A catalog read happens only after the complete parser output is valid.
        # It can create links to existing active skills, never a Skill/UserSkill.
        skill_terms = cls._skill_term_index(repository.skill_terms_for_matching())
        links_by_item_id = {
            item.id: cls._matched_skills(item.bullet_text, skill_terms)
            for item in evidence_items
        }

        # The repository flushes the old delete before new ordinals are staged, but
        # the single enclosing UnitOfWork still rolls it back if an insert fails.
        repository.replace_evidence_for_version(version.id, evidence_items)
        uow.session.flush()
        uow.session.add_all(
            ResumeEvidenceSkill(
                evidence_item_id=item.id,
                skill_id=skill_id,
                parser_confidence=Decimal("1.00"),
            )
            for item in evidence_items
            for skill_id, _ in links_by_item_id[item.id]
        )
        version.raw_extracted_text = parsed.raw_text
        version.parse_status = "PARSED_SUCCESS"
        uow.session.flush()
        result = ResumeVersionRead.model_validate(version)
        uow.commit()
        return result

    @staticmethod
    def get_evidence(owner: UUID, version_id: UUID, uow) -> list[ResumeEvidenceItemRead]:
        repository = ResumeRepository(uow.session)
        if repository.owned_version(owner, version_id) is None:
            raise _version_not_found()
        evidence = repository.evidence_for_owned_version(owner, version_id)
        skills_by_evidence_id: dict[UUID, list[ResumeEvidenceSkillRead]] = {
            item.id: [] for item in evidence
        }
        for evidence_item_id, skill_id, name, confidence in repository.skills_for_evidence_items(
            [item.id for item in evidence]
        ):
            skills_by_evidence_id[evidence_item_id].append(
                ResumeEvidenceSkillRead(
                    skill_id=skill_id,
                    name=name,
                    parser_confidence=confidence,
                )
            )
        return [
            ResumeEvidenceItemRead(
                id=item.id,
                resume_version_id=item.resume_version_id,
                ordinal=item.ordinal,
                category=item.category,
                section_header=item.section_header,
                bullet_text=item.bullet_text,
                recognized_skills=skills_by_evidence_id[item.id],
            )
            for item in evidence
        ]

    @staticmethod
    def get_extracted_text(owner: UUID, version_id: UUID, uow) -> ResumeExtractedTextRead:
        version = ResumeRepository(uow.session).owned_version(owner, version_id)
        if version is None:
            raise _version_not_found()
        # The empty value makes an unparsed owned version safe to inspect without
        # exposing storage state or triggering a parse through this GET endpoint.
        return ResumeExtractedTextRead(raw_extracted_text=version.raw_extracted_text or "")

    @staticmethod
    def select_primary(
        owner: UUID, resume_id: UUID, payload: ResumePrimaryVersionUpdate, uow
    ) -> ResumeVersionRead:
        repository = ResumeRepository(uow.session)
        resume = repository.owned_resume(owner, resume_id, lock=True)
        if resume is None:
            raise _not_found()
        version = repository.version_for_locked_resume(resume.id, payload.version_id, lock=True)
        if version is None:
            # Do not reveal whether the requested version belongs to another family or user.
            raise _version_not_found()
        # Flush demotions before promotion so PostgreSQL's partial unique index remains valid.
        repository.demote_other_primary_versions(resume.id, version.id)
        uow.session.flush()
        version.is_primary_active = True
        uow.session.flush()
        result = ResumeVersionRead.model_validate(version)
        uow.commit()
        return result

    @staticmethod
    def _mark_parse_failed(version: ResumeVersion, uow) -> ResumeVersionRead:
        """Commit only the safe retryable status; preserve earlier good evidence."""
        version.parse_status = "PARSE_FAILED"
        uow.session.flush()
        result = ResumeVersionRead.model_validate(version)
        uow.commit()
        return result

    @staticmethod
    def _normalized_skill_term(value: str) -> str:
        return " ".join(value.split()).casefold()

    @classmethod
    def _skill_term_index(
        cls, rows: list[tuple[UUID, str, str]]
    ) -> dict[str, tuple[UUID, str]]:
        """Keep only unambiguous exact catalog names or explicitly stored aliases."""
        candidates: dict[str, set[tuple[UUID, str]]] = {}
        for skill_id, name, term in rows:
            normalized = cls._normalized_skill_term(term)
            if normalized and name.strip():
                candidates.setdefault(normalized, set()).add((skill_id, name))
        return {
            term: next(iter(matches))
            for term, matches in candidates.items()
            if len(matches) == 1
        }

    @classmethod
    def _matched_skills(
        cls, evidence_text: str, skill_terms: dict[str, tuple[UUID, str]]
    ) -> list[tuple[UUID, str]]:
        normalized_text = cls._normalized_skill_term(evidence_text)
        matches: set[tuple[UUID, str]] = set()
        for term, skill in skill_terms.items():
            # A technology token must be separated from adjacent word/technology
            # characters, preventing matches such as Java inside JavaScript.
            if re.search(
                rf"(?<!{_SKILL_TERM_EDGE}){re.escape(term)}(?!{_SKILL_TERM_EDGE})",
                normalized_text,
            ):
                matches.add(skill)
        return sorted(matches, key=lambda skill: (skill[1].casefold(), str(skill[0])))

    @staticmethod
    def _validated_evidence_items(
        version_id: UUID, parsed: ParsedResume
    ) -> list[ResumeEvidenceItem]:
        """Validate the whole derived set before replacing any persisted evidence."""
        if not parsed.raw_text or len(parsed.raw_text) > MAX_EXTRACTED_TEXT_CHARS:
            raise ValueError("Invalid extracted text")
        items: list[ResumeEvidenceItem] = []
        for expected_ordinal, candidate in enumerate(parsed.evidence):
            if (
                candidate.ordinal != expected_ordinal
                or candidate.category not in EVIDENCE_CATEGORIES
                or not candidate.bullet_text.strip()
                or len(candidate.section_header or "") > 150
            ):
                raise ValueError("Invalid derived evidence")
            items.append(
                ResumeEvidenceItem(
                    id=uuid4(),
                    resume_version_id=version_id,
                    ordinal=candidate.ordinal,
                    category=candidate.category,
                    section_header=candidate.section_header,
                    bullet_text=candidate.bullet_text,
                )
            )
        return items

    @classmethod
    def read_file(cls, owner: UUID, version_id: UUID, uow) -> tuple[bytes, str, str]:
        repository = ResumeRepository(uow.session)
        version = repository.owned_version(owner, version_id)
        if version is None:
            raise _version_not_found()
        try:
            content = cls.storage_factory().open(version.storage_key)
        except (FileNotFoundError, ValueError) as error:
            # Same safe response as an unknown version; never expose a filesystem path or key.
            raise _version_not_found() from error
        resume = repository.owned_resume(owner, version.resume_id)
        if resume is None:
            raise _version_not_found()
        extension = "pdf" if version.file_format == "PDF" else "docx"
        safe_title = "".join(
            character
            for character in resume.title
            if character.isascii() and (character.isalnum() or character in " -_")
        ).strip() or "resume"
        return content, version.file_format, f"{safe_title}-v{version.version_number}.{extension}"

    @classmethod
    def delete_version(cls, owner: UUID, version_id: UUID, uow) -> None:
        repository = ResumeRepository(uow.session)
        initial = repository.owned_version(owner, version_id)
        if initial is None:
            raise _version_not_found()
        resume = repository.owned_resume(owner, initial.resume_id, lock=True)
        if resume is None:
            raise _version_not_found()
        version = repository.version_for_locked_resume(resume.id, version_id, lock=True)
        if version is None:
            raise _version_not_found()
        if repository.version_is_recorded_on_application(version.id):
            raise StudentSuccessfulException(
                409,
                "RESUME_VERSION_IN_USE",
                "This resume version is recorded on an application and cannot be deleted",
            )
        cls._delete_rows_then_cleanup_storage(uow, [version])

    @classmethod
    def delete_resume(cls, owner: UUID, resume_id: UUID, uow) -> None:
        repository = ResumeRepository(uow.session)
        resume = repository.owned_resume(owner, resume_id, lock=True)
        if resume is None:
            raise _not_found()
        versions = repository.versions_for_resume(resume.id)
        if any(repository.version_is_recorded_on_application(version.id) for version in versions):
            raise StudentSuccessfulException(
                409,
                "RESUME_VERSION_IN_USE",
                "A resume version is recorded on an application and cannot be deleted",
            )
        cls._delete_rows_then_cleanup_storage(uow, versions, aggregate=resume)

    @classmethod
    def _delete_rows_then_cleanup_storage(cls, uow, versions: list[ResumeVersion], aggregate=None) -> None:
        """Commit metadata removal before best-effort storage cleanup.

        Filesystems and PostgreSQL cannot share a transaction. Ordering the durable
        metadata deletion first means an ordinary storage failure cannot leave a live
        version row pointing to a missing file. A rare post-commit deletion failure is
        an orphan, which is safer than corrupting the logical version record.
        """
        storage: StorageAdapter = cls.storage_factory()
        # SQLAlchemy expires/deletes these ORM rows at commit, so retain only the
        # opaque server-generated keys needed for post-commit cleanup.
        storage_keys = [version.storage_key for version in versions]
        if aggregate is None:
            for version in versions:
                uow.session.delete(version)
        else:
            uow.session.delete(aggregate)
        uow.commit()
        for storage_key in storage_keys:
            cls._delete_quietly(storage, storage_key)

    @staticmethod
    def _delete_quietly(storage: StorageAdapter, storage_key: str) -> None:
        try:
            storage.delete(storage_key)
        except Exception:
            # The original persistence failure remains the useful caller error.
            pass
