"""Phase 8A managed-resume family, upload, ownership, and compensation coverage."""

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from unittest.mock import patch
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import settings
from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.core.storage import LocalStorageAdapter
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.main import app
from backend.app.models.resume import Resume, ResumeVersion
from backend.app.models.user import User
from backend.app.schemas.resume import ResumePrimaryVersionUpdate
from backend.app.services.resume import MAX_UPLOAD_BYTES, ResumeService
from backend.tests.test_portfolio import account

RESUMES = "/api/v1/resumes"
PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def docx() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("word/document.xml", "<w:document></w:document>")
    return output.getvalue()


def unsafe_docx() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("word/document.xml", "<w:document></w:document>")
        archive.writestr("../outside.txt", "not extracted")
    return output.getvalue()


def expanded_docx() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("word/document.xml", "<w:document></w:document>")
        archive.writestr("word/large.xml", b"0" * (26 * 1024 * 1024))
    return output.getvalue()


def create_resume(client: TestClient, title="Backend Resume") -> dict:
    response = client.post(RESUMES, json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()


def upload(client: TestClient, resume_id: str, filename="resume.pdf", content=PDF, content_type="application/pdf"):
    return client.post(
        f"{RESUMES}/{resume_id}/versions",
        files={"file": (filename, content, content_type)},
    )


def test_resume_family_crud_versions_primary_download_and_artifact_independence():
    client, _ = account()
    artifact = client.post(
        "/api/v1/artifacts",
        json={"title": "External Resume", "external_url": "https://example.com/resume.pdf"},
    ).json()
    assert client.get(RESUMES).json() == []
    first = create_resume(client)
    second = create_resume(client, "Systems Resume")
    assert client.get(RESUMES).json() == [first, second]
    assert client.patch(f"{RESUMES}/{first['id']}", json={"title": "Renamed Resume"}).json()["title"] == "Renamed Resume"

    v1 = upload(client, first["id"]).json()
    assert v1["version_number"] == 1 and v1["is_primary_active"] and v1["parse_status"] == "PENDING"
    assert "storage_key" not in v1 and "raw_extracted_text" not in v1
    docx_content = docx()
    v2_response = upload(client, first["id"], "resume.docx", docx_content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert v2_response.status_code == 201, v2_response.text
    v2 = v2_response.json()
    assert v2["version_number"] == 2 and not v2["is_primary_active"]
    assert [row["id"] for row in client.get(f"{RESUMES}/{first['id']}/versions").json()] == [v1["id"], v2["id"]]

    primary = client.put(f"{RESUMES}/{first['id']}/primary-version", json={"version_id": v2["id"]})
    assert primary.status_code == 200, primary.text
    versions = client.get(f"{RESUMES}/{first['id']}/versions").json()
    assert [row["is_primary_active"] for row in versions] == [False, True]
    file_response = client.get(f"/api/v1/resume-versions/{v2['id']}/file")
    assert file_response.status_code == 200
    assert file_response.headers["cache-control"] == "no-store"
    assert "attachment;" in file_response.headers["content-disposition"]
    assert "storage" not in file_response.text.lower()
    assert file_response.content == docx_content

    assert client.delete(f"/api/v1/resume-versions/{v2['id']}").status_code == 204
    remaining = client.get(f"{RESUMES}/{first['id']}/versions").json()
    assert len(remaining) == 1 and remaining[0]["is_primary_active"] is False
    assert client.delete(f"{RESUMES}/{first['id']}").status_code == 204
    assert client.get(RESUMES).json() == [second]
    assert client.get("/api/v1/artifacts").json() == [artifact]


@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        ("resume.txt", PDF, "application/pdf"),
        ("resume.pdf", b"not a PDF", "application/pdf"),
        ("resume.docx", b"not a zip", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("resume.pdf", docx(), "application/pdf"),
        ("resume.docx", PDF, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("resume.docx", unsafe_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("resume.pdf", PDF, "text/plain"),
        pytest.param(
            "resume.pdf",
            PDF + b"x" * MAX_UPLOAD_BYTES,
            "application/pdf",
            id="oversize-pdf",
        ),
    ],
)
def test_upload_validation_is_layered(filename, content, content_type):
    client, _ = account()
    resume = create_resume(client)
    response = upload(client, resume["id"], filename, content, content_type)
    assert response.status_code == 422, response.text
    assert client.get(f"{RESUMES}/{resume['id']}/versions").json() == []


def test_docx_expansion_limit_is_checked_without_extracting_files():
    with pytest.raises(StudentSuccessfulException, match="safe limit|unsafe compression"):
        ResumeService.validate_upload(
            "resume.docx",
            expanded_docx(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )


def test_owned_resources_csrf_and_safe_not_found_behavior():
    owner, _ = account()
    other, other_id = account()
    resume = create_resume(owner)
    version = upload(owner, resume["id"]).json()
    for method, path, payload in [
        ("GET", f"{RESUMES}/{resume['id']}", None),
        ("GET", f"{RESUMES}/{resume['id']}/versions", None),
        ("GET", f"/api/v1/resume-versions/{version['id']}", None),
        ("GET", f"/api/v1/resume-versions/{version['id']}/file", None),
        ("PATCH", f"{RESUMES}/{resume['id']}", {"title": "No"}),
        ("PUT", f"{RESUMES}/{resume['id']}/primary-version", {"version_id": version["id"]}),
        ("DELETE", f"/api/v1/resume-versions/{version['id']}", None),
        ("DELETE", f"{RESUMES}/{resume['id']}", None),
    ]:
        assert other.request(method, path, json=payload).status_code == 404
        assert TestClient(app).request(method, path, json=payload).status_code == 401
        if method not in {"GET"}:
            assert owner.request(method, path, json=payload, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert owner.get(RESUMES + f"?user_id={other_id}").status_code == 422
    assert owner.post(RESUMES, json={"title": "No client owner", "user_id": str(other_id)}).status_code == 422


def test_primary_selection_rejects_a_version_from_another_owned_resume_family():
    """A valid owned version may not be promoted across resume-family boundaries."""
    client, _ = account()
    first = create_resume(client, "Backend Resume")
    second = create_resume(client, "Systems Resume")
    foreign_version = upload(client, second["id"]).json()

    response = client.put(
        f"{RESUMES}/{first['id']}/primary-version",
        json={"version_id": foreign_version["id"]},
    )

    assert response.status_code == 404
    assert client.get(f"{RESUMES}/{first['id']}/versions").json() == []
    assert client.get(f"{RESUMES}/{second['id']}/versions").json() == [foreign_version]


def test_missing_stored_file_has_a_safe_not_found_response(isolated_database):
    client, _ = account()
    resume = create_resume(client)
    version = upload(client, resume["id"]).json()
    row = isolated_database.execute(
        select(ResumeVersion.storage_key).where(ResumeVersion.id == UUID(version["id"]))
    ).scalar_one()
    LocalStorageAdapter(settings.STORAGE_LOCAL_ROOT).delete(row)
    response = client.get(f"/api/v1/resume-versions/{version['id']}/file")
    assert response.status_code == 404
    assert settings.STORAGE_LOCAL_ROOT not in response.text


def test_download_filename_is_header_safe_for_non_ascii_resume_titles():
    client, _ = account()
    resume = create_resume(client, "R\u00e9sum\u00e9 \u2603")
    version = upload(client, resume["id"]).json()
    response = client.get(f"/api/v1/resume-versions/{version['id']}/file")
    assert response.status_code == 200
    assert "filename=\"Rsum-v1.pdf\"" in response.headers["content-disposition"]


def test_upload_commit_failure_compensates_the_stored_file(tmp_path):
    client, _ = account()
    resume = create_resume(client)
    original = UnitOfWork.commit
    with patch.object(UnitOfWork, "commit", autospec=True, side_effect=RuntimeError("db failed")):
        with pytest.raises(RuntimeError, match="db failed"):
            upload(client, resume["id"])
    assert not [path for path in (tmp_path / "storage").rglob("*") if path.is_file()]
    assert client.get(f"{RESUMES}/{resume['id']}/versions").json() == []
    assert original is not None


def test_partially_written_upload_is_cleaned_when_storage_raises():
    class PartiallyWritingStorage:
        def __init__(self):
            self.saved_key: str | None = None
            self.deleted: list[str] = []

        def save(self, storage_key: str, data: bytes) -> str:
            self.saved_key = storage_key
            raise OSError("storage interrupted after a partial write")

        def delete(self, storage_key: str) -> None:
            self.deleted.append(storage_key)

        def open(self, storage_key: str) -> bytes:  # pragma: no cover - protocol completeness
            raise FileNotFoundError

        def health_check(self) -> bool:  # pragma: no cover - protocol completeness
            return True

    client, _ = account()
    resume = create_resume(client)
    storage = PartiallyWritingStorage()
    with patch.object(ResumeService, "storage_factory", return_value=storage):
        with pytest.raises(OSError, match="partial write"):
            upload(client, resume["id"])
    assert storage.saved_key is not None
    assert storage.deleted == [storage.saved_key]
    assert client.get(f"{RESUMES}/{resume['id']}/versions").json() == []


def test_delete_commit_failure_restores_file_and_row(tmp_path):
    client, _ = account()
    resume = create_resume(client)
    version = upload(client, resume["id"]).json()
    storage_files = [path for path in (tmp_path / "storage").rglob("*") if path.is_file()]
    assert len(storage_files) == 1
    with patch.object(UnitOfWork, "commit", autospec=True, side_effect=RuntimeError("db failed")):
        with pytest.raises(RuntimeError, match="db failed"):
            client.delete(f"/api/v1/resume-versions/{version['id']}")
    assert len([path for path in (tmp_path / "storage").rglob("*") if path.is_file()]) == 1
    assert client.get(f"/api/v1/resume-versions/{version['id']}").status_code == 200


def test_concurrent_uploads_allocate_unique_sequential_versions(database_engine, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "STORAGE_LOCAL_ROOT", str(tmp_path / "storage"))
    factory = sessionmaker(bind=database_engine, expire_on_commit=False)
    owner = uuid4()
    resume_id = uuid4()
    with factory.begin() as session:
        session.add(User(id=owner, email=f"resume-{owner}@example.com", password_hash="test"))
        session.flush()
        session.add(Resume(id=resume_id, user_id=owner, title="Concurrent Resume"))

    def create_version(index: int):
        with UnitOfWork(factory) as uow:
            return ResumeService.upload_version(
                owner, resume_id, f"resume-{index}.pdf", PDF, "application/pdf", uow
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            created = list(executor.map(create_version, [1, 2]))
        assert sorted(version.version_number for version in created) == [1, 2]
        with factory() as session:
            versions = list(session.scalars(select(ResumeVersion).where(ResumeVersion.resume_id == resume_id)))
            assert sorted(version.version_number for version in versions) == [1, 2]
            assert sum(version.is_primary_active for version in versions) == 1
    finally:
        with factory.begin() as session:
            session.execute(delete(User).where(User.id == owner))


def test_concurrent_primary_selection_leaves_exactly_one_primary(
    database_engine, monkeypatch, tmp_path
):
    """The aggregate lock serializes conflicting primary-version selections."""
    monkeypatch.setattr(settings, "STORAGE_LOCAL_ROOT", str(tmp_path / "storage"))
    factory = sessionmaker(bind=database_engine, expire_on_commit=False)
    owner = uuid4()
    resume_id = uuid4()
    with factory.begin() as session:
        session.add(User(id=owner, email=f"primary-{owner}@example.com", password_hash="test"))
        session.flush()
        session.add(Resume(id=resume_id, user_id=owner, title="Primary Resume"))

    def add_version(index: int):
        with UnitOfWork(factory) as uow:
            return ResumeService.upload_version(
                owner, resume_id, f"resume-{index}.pdf", PDF, "application/pdf", uow
            )

    def choose_primary(version_id):
        with UnitOfWork(factory) as uow:
            return ResumeService.select_primary(
                owner,
                resume_id,
                ResumePrimaryVersionUpdate(version_id=version_id),
                uow,
            )

    try:
        first, second = add_version(1), add_version(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            selected = list(executor.map(choose_primary, [first.id, second.id]))
        assert {item.id for item in selected} == {first.id, second.id}
        with factory() as session:
            versions = list(
                session.scalars(select(ResumeVersion).where(ResumeVersion.resume_id == resume_id))
            )
            primary = [version for version in versions if version.is_primary_active]
            assert len(primary) == 1
            assert primary[0].id in {first.id, second.id}
    finally:
        with factory.begin() as session:
            session.execute(delete(User).where(User.id == owner))
