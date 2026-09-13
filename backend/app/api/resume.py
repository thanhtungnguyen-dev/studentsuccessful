"""Authenticated managed resume-family and immutable file-version API."""

from __future__ import annotations

from email.parser import BytesParser
from email.policy import default
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from backend.app.api.deps import get_current_user, get_uow, require_csrf
from backend.app.api.employment import reject_owner_query
from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.schemas.common import ProblemDetail
from backend.app.schemas.resume import (
    ResumeCreate,
    ResumeEvidenceItemRead,
    ResumeExtractedTextRead,
    ResumePrimaryVersionUpdate,
    ResumeRead,
    ResumeUpdate,
    ResumeVersionRead,
)
from backend.app.services.resume import MAX_UPLOAD_BYTES, ResumeService

router = APIRouter(
    tags=["resumes"],
    dependencies=[Depends(reject_owner_query)],
    responses={
        401: {"model": ProblemDetail},
        403: {"model": ProblemDetail},
        404: {"model": ProblemDetail},
        409: {"model": ProblemDetail},
    },
)

# The standard library parser needs a bounded complete MIME entity. This leaves room for
# a browser multipart boundary and headers while the decoded file remains strictly <= 5 MiB.
MAX_MULTIPART_BODY_BYTES = MAX_UPLOAD_BYTES + 128 * 1024
MULTIPART_FILE_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {"file": {"type": "string", "format": "binary"}},
                }
            }
        },
    }
}


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _invalid_multipart(detail: str) -> StudentSuccessfulException:
    return StudentSuccessfulException(422, "INVALID_RESUME_UPLOAD", detail)


async def _read_bounded_request_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_MULTIPART_BODY_BYTES:
                raise _invalid_multipart("Resume files must be 5 MB or smaller")
        except ValueError as error:
            raise _invalid_multipart("Invalid upload content length") from error
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_MULTIPART_BODY_BYTES:
            raise _invalid_multipart("Resume files must be 5 MB or smaller")
        chunks.append(chunk)
    return b"".join(chunks)


async def parse_single_resume_upload(request: Request) -> tuple[str | None, bytes, str | None]:
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data;") or "boundary=" not in content_type:
        raise _invalid_multipart("Upload must use multipart/form-data")
    try:
        header = content_type.encode("latin-1")
    except UnicodeEncodeError as error:
        raise _invalid_multipart("Invalid upload content type") from error
    body = await _read_bounded_request_body(request)
    try:
        message = BytesParser(policy=default).parsebytes(
            b"Content-Type: " + header + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
        )
        if message.defects or not message.is_multipart():
            raise _invalid_multipart("Malformed multipart upload")
        parts = list(message.iter_parts())
        if len(parts) != 1:
            raise _invalid_multipart("Upload exactly one file")
        part = parts[0]
        if part.defects or part.get_content_disposition() != "form-data":
            raise _invalid_multipart("Malformed multipart upload")
        if part.get_param("name", header="content-disposition") != "file":
            raise _invalid_multipart("Upload exactly one file named file")
        transfer_encoding = (part.get("Content-Transfer-Encoding") or "").lower()
        if transfer_encoding not in {"", "binary", "8bit", "7bit"}:
            raise _invalid_multipart("Unsupported upload transfer encoding")
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            raise _invalid_multipart("Malformed multipart upload")
        declared_content_type = part.get_content_type() if part.get("Content-Type") else None
        return part.get_filename(), payload, declared_content_type
    except StudentSuccessfulException:
        raise
    except (ValueError, UnicodeError) as error:
        raise _invalid_multipart("Malformed multipart upload") from error


@router.get("/resumes", response_model=list[ResumeRead])
def list_resumes(response: Response, user=Depends(get_current_user), uow=Depends(get_uow)):
    no_store(response)
    return ResumeService.list(user.id, uow)


@router.post("/resumes", response_model=ResumeRead, status_code=201)
def create_resume(
    payload: ResumeCreate,
    response: Response,
    authenticated=Depends(require_csrf),
    uow=Depends(get_uow),
):
    no_store(response)
    return ResumeService.create(authenticated[0].id, payload, uow)


@router.get("/resumes/{id}", response_model=ResumeRead)
def get_resume(id: UUID, response: Response, user=Depends(get_current_user), uow=Depends(get_uow)):
    no_store(response)
    return ResumeService.get(user.id, id, uow)


@router.patch("/resumes/{id}", response_model=ResumeRead)
def update_resume(
    id: UUID,
    payload: ResumeUpdate,
    response: Response,
    authenticated=Depends(require_csrf),
    uow=Depends(get_uow),
):
    no_store(response)
    return ResumeService.update(authenticated[0].id, id, payload, uow)


@router.delete("/resumes/{id}", status_code=204)
def delete_resume(id: UUID, authenticated=Depends(require_csrf), uow=Depends(get_uow)):
    ResumeService.delete_resume(authenticated[0].id, id, uow)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/resumes/{id}/versions", response_model=list[ResumeVersionRead])
def list_resume_versions(
    id: UUID, response: Response, user=Depends(get_current_user), uow=Depends(get_uow)
):
    no_store(response)
    return ResumeService.list_versions(user.id, id, uow)


@router.post(
    "/resumes/{id}/versions",
    response_model=ResumeVersionRead,
    status_code=201,
    openapi_extra=MULTIPART_FILE_BODY,
)
async def upload_resume_version(
    id: UUID,
    request: Request,
    response: Response,
    authenticated=Depends(require_csrf),
    uow=Depends(get_uow),
):
    no_store(response)
    filename, content, declared_content_type = await parse_single_resume_upload(request)
    return ResumeService.upload_version(
        authenticated[0].id, id, filename, content, declared_content_type, uow
    )


@router.put("/resumes/{id}/primary-version", response_model=ResumeVersionRead)
def select_primary_version(
    id: UUID,
    payload: ResumePrimaryVersionUpdate,
    response: Response,
    authenticated=Depends(require_csrf),
    uow=Depends(get_uow),
):
    no_store(response)
    return ResumeService.select_primary(authenticated[0].id, id, payload, uow)


@router.get("/resume-versions/{id}", response_model=ResumeVersionRead)
def get_resume_version(
    id: UUID, response: Response, user=Depends(get_current_user), uow=Depends(get_uow)
):
    no_store(response)
    return ResumeService.get_version(user.id, id, uow)


@router.post("/resume-versions/{id}/parse", response_model=ResumeVersionRead)
def parse_resume_version(
    id: UUID,
    response: Response,
    authenticated=Depends(require_csrf),
    uow=Depends(get_uow),
):
    """Explicitly parse one owned immutable upload into version-scoped evidence."""
    no_store(response)
    return ResumeService.parse_version(authenticated[0].id, id, uow)


@router.get("/resume-versions/{id}/evidence", response_model=list[ResumeEvidenceItemRead])
def get_resume_evidence(
    id: UUID, response: Response, user=Depends(get_current_user), uow=Depends(get_uow)
):
    no_store(response)
    return ResumeService.get_evidence(user.id, id, uow)


@router.get("/resume-versions/{id}/extracted-text", response_model=ResumeExtractedTextRead)
def get_resume_extracted_text(
    id: UUID, response: Response, user=Depends(get_current_user), uow=Depends(get_uow)
):
    no_store(response)
    return ResumeService.get_extracted_text(user.id, id, uow)


@router.delete("/resume-versions/{id}", status_code=204)
def delete_resume_version(id: UUID, authenticated=Depends(require_csrf), uow=Depends(get_uow)):
    ResumeService.delete_version(authenticated[0].id, id, uow)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/resume-versions/{id}/file")
def download_resume_version(
    id: UUID, user=Depends(get_current_user), uow=Depends(get_uow)
):
    content, file_format, filename = ResumeService.read_file(user.id, id, uow)
    media_type = (
        "application/pdf"
        if file_format == "PDF"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
