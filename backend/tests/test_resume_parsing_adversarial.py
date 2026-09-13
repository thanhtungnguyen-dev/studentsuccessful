"""Adversarial API and transaction coverage for Phase 8B resume parsing."""

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier
from unittest.mock import patch
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import settings
from backend.app.core.storage import LocalStorageAdapter
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.main import app
from backend.app.models.base import Base
from backend.app.models.resume import (
    Resume,
    ResumeEvidenceItem,
    ResumeVersion,
    UserSkill,
)
from backend.app.models.taxonomy import Skill, SkillAlias
from backend.app.models.user import User
from backend.app.parsers.resume import ParsedEvidence, ParsedResume, ResumeParser
from backend.app.repositories.resume import ResumeRepository
from backend.app.services.resume import ResumeService
from backend.tests.test_portfolio import account

RESUMES = "/api/v1/resumes"
VERSION_ROOT = "/api/v1/resume-versions"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def docx(*paragraphs: str) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs)
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", xml)
    return output.getvalue()


def malformed_docx() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", b"<w:document")
    return output.getvalue()


def create_resume(client: TestClient, title: str = "Adversarial Resume") -> dict:
    response = client.post(RESUMES, json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()


def upload_docx(client: TestClient, resume_id: str, content: bytes) -> dict:
    response = client.post(
        f"{RESUMES}/{resume_id}/versions",
        files={"file": ("resume.docx", content, DOCX_CONTENT_TYPE)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def parse(client: TestClient, version_id: str):
    return client.post(f"{VERSION_ROOT}/{version_id}/parse")


def evidence_shape(client: TestClient, version_id: str) -> list[tuple[int, str, str, str | None]]:
    response = client.get(f"{VERSION_ROOT}/{version_id}/evidence")
    assert response.status_code == 200, response.text
    return [
        (item["ordinal"], item["category"], item["bullet_text"], item["section_header"])
        for item in response.json()
    ]


def test_corrupt_but_upload_valid_documents_fail_safely_without_evidence():
    client, _ = account()
    resume = create_resume(client)
    corrupt_pdf = b"%PDF-1.7\nthis is not a real PDF\n%%EOF\n"
    pdf_response = client.post(
        f"{RESUMES}/{resume['id']}/versions",
        files={"file": ("corrupt.pdf", corrupt_pdf, "application/pdf")},
    )
    assert pdf_response.status_code == 201, pdf_response.text
    malformed = upload_docx(client, resume["id"], malformed_docx())

    for version in (pdf_response.json(), malformed):
        response = parse(client, version["id"])
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["parse_status"] == "PARSE_FAILED"
        assert evidence_shape(client, version["id"]) == []
        assert client.get(f"{VERSION_ROOT}/{version['id']}/extracted-text").json() == {
            "raw_extracted_text": ""
        }
        assert "Traceback" not in response.text


def test_failed_reparse_preserves_good_raw_text_and_evidence_then_retry_replaces_them():
    client, _ = account()
    resume = create_resume(client)
    version = upload_docx(client, resume["id"], docx("Skills", "Python", "Projects", "Parser"))
    assert parse(client, version["id"]).json()["parse_status"] == "PARSED_SUCCESS"
    before_evidence = evidence_shape(client, version["id"])
    before_text = client.get(f"{VERSION_ROOT}/{version['id']}/extracted-text").json()

    malformed_result = ParsedResume(
        raw_text="Replacement text",
        evidence=(
            ParsedEvidence(0, "SKILLS", "Skills", "Python"),
            ParsedEvidence(1, "NOT_A_CATEGORY", "Broken", "Must not persist"),
        ),
    )
    with patch.object(ResumeParser, "parse", return_value=malformed_result):
        response = parse(client, version["id"])
    assert response.status_code == 200
    assert response.json()["parse_status"] == "PARSE_FAILED"
    assert evidence_shape(client, version["id"]) == before_evidence
    assert client.get(f"{VERSION_ROOT}/{version['id']}/extracted-text").json() == before_text

    with patch.object(ResumeParser, "parse", side_effect=RuntimeError("private parser internals")):
        response = parse(client, version["id"])
    assert response.status_code == 200
    assert response.json()["parse_status"] == "PARSE_FAILED"
    assert "private parser internals" not in response.text
    assert evidence_shape(client, version["id"]) == before_evidence
    assert client.get(f"{VERSION_ROOT}/{version['id']}/extracted-text").json() == before_text

    retry = parse(client, version["id"])
    assert retry.status_code == 200 and retry.json()["parse_status"] == "PARSED_SUCCESS"
    assert evidence_shape(client, version["id"]) == before_evidence


def test_missing_managed_file_marks_failure_but_leaks_no_storage_detail(isolated_database):
    client, _ = account()
    resume = create_resume(client)
    version = upload_docx(client, resume["id"], docx("Skills", "Python"))
    storage_key = isolated_database.execute(
        select(ResumeVersion.storage_key).where(ResumeVersion.id == UUID(version["id"]))
    ).scalar_one()
    LocalStorageAdapter(settings.STORAGE_LOCAL_ROOT).delete(storage_key)

    response = parse(client, version["id"])
    assert response.status_code == 404
    assert response.json()["code"] == "RESUME_VERSION_NOT_FOUND"
    assert settings.STORAGE_LOCAL_ROOT not in response.text
    assert storage_key not in response.text
    assert client.get(f"{VERSION_ROOT}/{version['id']}").json()["parse_status"] == "PARSE_FAILED"
    assert evidence_shape(client, version["id"]) == []


def test_gets_are_side_effect_free_and_parse_routes_enforce_owner_csrf_and_no_user_id():
    owner, _ = account()
    other, other_id = account()
    resume = create_resume(owner)
    version = upload_docx(owner, resume["id"], docx("Skills", "Python"))
    version_path = f"{VERSION_ROOT}/{version['id']}"

    assert owner.get(version_path).json()["parse_status"] == "PENDING"
    evidence_response = owner.get(f"{version_path}/evidence")
    assert evidence_response.status_code == 200
    assert evidence_response.headers["cache-control"] == "no-store"
    assert evidence_response.json() == []
    text_response = owner.get(f"{version_path}/extracted-text")
    assert text_response.headers["cache-control"] == "no-store"
    assert text_response.json() == {"raw_extracted_text": ""}
    assert owner.get(version_path).json()["parse_status"] == "PENDING"

    for suffix in ("/parse", "/evidence", "/extracted-text"):
        method = "POST" if suffix == "/parse" else "GET"
        assert other.request(method, version_path + suffix).status_code == 404
        assert TestClient(app).request(method, version_path + suffix).status_code == 401
    assert owner.post(version_path + "/parse", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert owner.post(version_path + f"/parse?user_id={other_id}").status_code == 422
    assert owner.get(version_path + f"/evidence?user_id={other_id}").status_code == 422
    assert owner.get(version_path).json()["parse_status"] == "PENDING"


def test_skill_evidence_uses_exact_catalog_names_or_unambiguous_aliases_only(isolated_database):
    client, owner_id = account()
    skills = [
        (uuid4(), "Java", "java"),
        (uuid4(), "JavaScript", "javascript"),
        (uuid4(), "C++", "cplusplus"),
        (uuid4(), "C#", "csharp"),
        (uuid4(), "PostgreSQL", "postgresql"),
        (uuid4(), "Machine Learning", "machine-learning"),
        (uuid4(), "Management Leadership", "management-leadership"),
    ]
    isolated_database.execute(
        Skill.__table__.insert(),
        [
            {"id": skill_id, "name": name, "slug": slug, "category": "TECHNOLOGY"}
            for skill_id, name, slug in skills
        ],
    )
    skill_id_by_name = {name: skill_id for skill_id, name, _ in skills}
    isolated_database.execute(
        SkillAlias.__table__.insert(),
        [
            {
                "skill_id": skill_id_by_name["PostgreSQL"],
                "alias": "Postgres",
                "normalized_alias": "postgres",
            },
            {
                "skill_id": skill_id_by_name["Machine Learning"],
                "alias": "ML",
                "normalized_alias": "ml",
            },
            {
                "skill_id": skill_id_by_name["Management Leadership"],
                "alias": "ML",
                "normalized_alias": "ml",
            },
        ],
    )
    resume = create_resume(client)
    version = upload_docx(
        client,
        resume["id"],
        # Java must not be detected merely because JavaScript is present. C++
        # and C# exercise punctuation-aware boundaries, Postgres is an explicit
        # alias, and ML is intentionally ambiguous across two catalog skills.
        docx("Technical Skills", "JavaScript C++ C# Postgres ML"),
    )

    assert parse(client, version["id"]).json()["parse_status"] == "PARSED_SUCCESS"
    response = client.get(f"{VERSION_ROOT}/{version['id']}/evidence")
    assert response.status_code == 200
    evidence = response.json()
    assert len(evidence) == 1
    assert {skill["name"] for skill in evidence[0]["recognized_skills"]} == {
        "JavaScript",
        "C++",
        "C#",
        "PostgreSQL",
    }
    assert "Java" not in {skill["name"] for skill in evidence[0]["recognized_skills"]}
    assert "Machine Learning" not in {
        skill["name"] for skill in evidence[0]["recognized_skills"]
    }
    assert isolated_database.execute(
        select(UserSkill).where(UserSkill.user_id == owner_id)
    ).scalars().all() == []


def test_reparse_is_idempotent_and_categories_are_complete_without_duplicate_evidence():
    client, _ = account()
    resume = create_resume(client)
    version = upload_docx(
        client,
        resume["id"],
        docx(
            "Summary",
            "Conservative unknown material",
            "Education",
            "BSc Computer Science",
            "Professional Experience",
            "Built services",
            "Projects",
            "Resume parser",
            "Technical Skills",
            "Python, Docker",
        ),
    )
    assert parse(client, version["id"]).json()["parse_status"] == "PARSED_SUCCESS"
    first = evidence_shape(client, version["id"])
    assert [item[0] for item in first] == list(range(len(first)))
    assert {item[1] for item in first} == {
        "OTHER",
        "EDUCATION",
        "EXPERIENCE",
        "PROJECTS",
        "SKILLS",
    }
    assert len({(item[0], item[1], item[2]) for item in first}) == len(first)

    assert parse(client, version["id"]).json()["parse_status"] == "PARSED_SUCCESS"
    assert evidence_shape(client, version["id"]) == first


def test_parsed_evidence_stays_version_scoped_and_persists_to_an_independent_session(
    database_engine, monkeypatch, tmp_path
):
    """Parsing v2 must not replace v1, and committed results outlive the UoW."""
    monkeypatch.setattr(settings, "STORAGE_LOCAL_ROOT", str(tmp_path / "storage"))
    factory = sessionmaker(bind=database_engine, expire_on_commit=False)
    owner = uuid4()
    resume_id = uuid4()
    with factory.begin() as session:
        session.add(User(id=owner, email=f"versions-{owner}@example.com", password_hash="test"))
        session.flush()
        session.add(Resume(id=resume_id, user_id=owner, title="Versioned evidence"))

    try:
        with UnitOfWork(factory) as uow:
            version_one = ResumeService.upload_version(
                owner,
                resume_id,
                "version-one.docx",
                docx("Skills", "Python", "Projects", "First version"),
                DOCX_CONTENT_TYPE,
                uow,
            )
        with UnitOfWork(factory) as uow:
            ResumeService.parse_version(owner, version_one.id, uow)

        # A fresh session captures the complete committed v1 state before v2 exists.
        with factory() as session:
            v1_before = session.get(ResumeVersion, version_one.id)
            assert v1_before is not None
            before = (
                v1_before.parse_status,
                v1_before.raw_extracted_text,
                [
                    (item.id, item.ordinal, item.category, item.bullet_text)
                    for item in session.scalars(
                        select(ResumeEvidenceItem)
                        .where(ResumeEvidenceItem.resume_version_id == version_one.id)
                        .order_by(ResumeEvidenceItem.ordinal)
                    )
                ],
            )

        with UnitOfWork(factory) as uow:
            version_two = ResumeService.upload_version(
                owner,
                resume_id,
                "version-two.docx",
                docx("Education", "BSc Computer Science", "Skills", "Docker"),
                DOCX_CONTENT_TYPE,
                uow,
            )
        with UnitOfWork(factory) as uow:
            ResumeService.parse_version(owner, version_two.id, uow)

        # Another independent session proves both commits persisted and v1 retained
        # its original evidence identifiers, order, text, and extracted text.
        with factory() as session:
            v1_after = session.get(ResumeVersion, version_one.id)
            v2_after = session.get(ResumeVersion, version_two.id)
            assert v1_after is not None and v2_after is not None
            assert (v1_after.parse_status, v1_after.raw_extracted_text) == before[:2]
            assert [
                (item.id, item.ordinal, item.category, item.bullet_text)
                for item in session.scalars(
                    select(ResumeEvidenceItem)
                    .where(ResumeEvidenceItem.resume_version_id == version_one.id)
                    .order_by(ResumeEvidenceItem.ordinal)
                )
            ] == before[2]
            assert v2_after.version_number == 2
            assert v2_after.parse_status == "PARSED_SUCCESS"
            assert v2_after.raw_extracted_text == "Education\nBSc Computer Science\nSkills\nDocker"
            assert [
                (item.ordinal, item.category, item.bullet_text)
                for item in session.scalars(
                    select(ResumeEvidenceItem)
                    .where(ResumeEvidenceItem.resume_version_id == version_two.id)
                    .order_by(ResumeEvidenceItem.ordinal)
                )
            ] == [(0, "EDUCATION", "BSc Computer Science"), (1, "SKILLS", "Docker")]
    finally:
        with factory.begin() as session:
            session.execute(delete(User).where(User.id == owner))


def test_parse_is_serialized_for_one_version_and_commits_one_complete_evidence_set(
    database_engine, monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "STORAGE_LOCAL_ROOT", str(tmp_path / "storage"))
    factory = sessionmaker(bind=database_engine, expire_on_commit=False)
    owner = uuid4()
    resume_id = uuid4()
    content = docx("Skills", "Python", "Projects", "Concurrent parser")
    with factory.begin() as session:
        session.add(User(id=owner, email=f"parse-{owner}@example.com", password_hash="test"))
        session.flush()
        session.add(Resume(id=resume_id, user_id=owner, title="Concurrent parse"))

    try:
        with UnitOfWork(factory) as uow:
            version = ResumeService.upload_version(
                owner, resume_id, "concurrent.docx", content, DOCX_CONTENT_TYPE, uow
            )
        barrier = Barrier(2)

        def parse_in_own_transaction():
            barrier.wait()
            with UnitOfWork(factory) as uow:
                return ResumeService.parse_version(owner, version.id, uow)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: parse_in_own_transaction(), range(2)))
        assert [result.parse_status for result in results] == ["PARSED_SUCCESS", "PARSED_SUCCESS"]
        with factory() as session:
            saved = session.get(ResumeVersion, version.id)
            assert saved is not None
            assert saved.parse_status == "PARSED_SUCCESS"
            assert saved.raw_extracted_text == "Skills\nPython\nProjects\nConcurrent parser"
            items = list(
                session.scalars(
                    select(ResumeEvidenceItem)
                    .where(ResumeEvidenceItem.resume_version_id == version.id)
                    .order_by(ResumeEvidenceItem.ordinal)
                )
            )
            assert [(item.ordinal, item.category, item.bullet_text) for item in items] == [
                (0, "SKILLS", "Python"),
                (1, "PROJECTS", "Concurrent parser"),
            ]
    finally:
        with factory.begin() as session:
            session.execute(delete(User).where(User.id == owner))


def test_database_failure_after_evidence_delete_rolls_back_to_the_previous_complete_set(
    database_engine, monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "STORAGE_LOCAL_ROOT", str(tmp_path / "storage"))
    factory = sessionmaker(bind=database_engine, expire_on_commit=False)
    owner = uuid4()
    resume_id = uuid4()
    content = docx("Skills", "Python", "Projects", "Rollback parser")
    with factory.begin() as session:
        session.add(User(id=owner, email=f"rollback-{owner}@example.com", password_hash="test"))
        session.flush()
        session.add(Resume(id=resume_id, user_id=owner, title="Rollback Resume"))

    try:
        with UnitOfWork(factory) as uow:
            version = ResumeService.upload_version(
                owner, resume_id, "rollback.docx", content, DOCX_CONTENT_TYPE, uow
            )
        with UnitOfWork(factory) as uow:
            ResumeService.parse_version(owner, version.id, uow)
        with factory() as session:
            before = [
                (row.id, row.ordinal, row.category, row.bullet_text)
                for row in session.scalars(
                    select(ResumeEvidenceItem)
                    .where(ResumeEvidenceItem.resume_version_id == version.id)
                    .order_by(ResumeEvidenceItem.ordinal)
                )
            ]
            before_raw_text = session.get(ResumeVersion, version.id).raw_extracted_text

        original_replace = ResumeRepository.replace_evidence_for_version

        def fail_after_replace(self, version_id, items):
            original_replace(self, version_id, items)
            raise RuntimeError("forced persistence interruption")

        with patch.object(ResumeRepository, "replace_evidence_for_version", fail_after_replace):
            with pytest.raises(RuntimeError, match="forced persistence interruption"):
                with UnitOfWork(factory) as uow:
                    ResumeService.parse_version(owner, version.id, uow)

        with factory() as session:
            saved = session.get(ResumeVersion, version.id)
            assert saved is not None
            assert saved.parse_status == "PARSED_SUCCESS"
            assert saved.raw_extracted_text == before_raw_text
            assert [
                (row.id, row.ordinal, row.category, row.bullet_text)
                for row in session.scalars(
                    select(ResumeEvidenceItem)
                    .where(ResumeEvidenceItem.resume_version_id == version.id)
                    .order_by(ResumeEvidenceItem.ordinal)
                )
            ] == before
    finally:
        with factory.begin() as session:
            session.execute(delete(User).where(User.id == owner))


def test_parsing_mutates_only_version_derived_tables_and_never_candidate_facts(isolated_database):
    client, _ = account()
    writes = [
        ("PATCH", "/api/v1/profile", {"legal_first_name": "Ada", "legal_last_name": "Lovelace"}),
        (
            "POST",
            "/api/v1/profile/education",
            {
                "institution_name": "Example University",
                "degree_level": "BS",
                "major": "Computing",
                "study_year": "YEAR_2",
                "start_date": "2025-01-01",
                "expected_grad_month": 5,
                "expected_grad_year": 2028,
            },
        ),
        (
            "POST",
            "/api/v1/profile/employment",
            {
                "employer_name": "Example Employer",
                "job_title": "Developer",
                "start_date": "2026-01-01",
                "currently_employed": True,
            },
        ),
        ("PUT", "/api/v1/profile/skills", {"custom_values": ["Explicit ability"]}),
        (
            "POST",
            "/api/v1/profile/projects",
            {"title": "Existing project", "technologies": {"custom_values": ["Project tech"]}},
        ),
        ("PUT", "/api/v1/preferences", {"custom_values": [{"preference_type": "SKILL", "value": "Interest"}]}),
        (
            "POST",
            "/api/v1/artifacts",
            {"title": "External Resume", "external_url": "https://example.com/resume.pdf"},
        ),
    ]
    for method, path, body in writes:
        response = client.request(method, path, json=body)
        assert response.status_code in {200, 201}, response.text
    resume = create_resume(client)
    version = upload_docx(client, resume["id"], docx("Skills", "Python"))

    ignored = {
        "resumes",
        "resume_versions",
        "resume_evidence_items",
        "resume_evidence_skills",
    }

    def snapshot():
        return {
            table.name: list(isolated_database.execute(select(table)).mappings())
            for table in Base.metadata.sorted_tables
            if table.name not in ignored
        }

    before = snapshot()
    response = parse(client, version["id"])
    assert response.status_code == 200 and response.json()["parse_status"] == "PARSED_SUCCESS"
    assert snapshot() == before
