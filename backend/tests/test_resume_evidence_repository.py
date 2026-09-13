"""PostgreSQL coverage for Phase 8B evidence provenance and repository boundaries."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models.resume import (
    Resume,
    ResumeEvidenceItem,
    ResumeEvidenceSkill,
    ResumeVersion,
    UserSkill,
)
from backend.app.models.taxonomy import Skill
from backend.app.models.user import User
from backend.app.repositories.resume import ResumeRepository


@pytest.fixture
def evidence_graph(isolated_database):
    session = Session(bind=isolated_database, join_transaction_mode="create_savepoint")
    owner = User(email=f"owner-{uuid4()}@example.edu", password_hash="test-only")
    other = User(email=f"other-{uuid4()}@example.edu", password_hash="test-only")
    skill = Skill(name="Python", slug=f"python-{uuid4()}", category="LANGUAGE")
    session.add_all([owner, other, skill])
    session.flush()
    resume = Resume(user_id=owner.id, title="Backend Resume")
    other_resume = Resume(user_id=other.id, title="Other Resume")
    session.add_all([resume, other_resume])
    session.flush()
    version = ResumeVersion(
        resume_id=resume.id,
        version_number=1,
        storage_key=f"resumes/{uuid4()}.pdf",
        file_format="PDF",
        file_size_bytes=16,
        file_hash_sha256="a" * 64,
    )
    other_version = ResumeVersion(
        resume_id=other_resume.id,
        version_number=1,
        storage_key=f"resumes/{uuid4()}.pdf",
        file_format="PDF",
        file_size_bytes=16,
        file_hash_sha256="b" * 64,
    )
    session.add_all([version, other_version])
    session.flush()
    yield session, owner, other, skill, version, other_version
    session.close()


def item(version_id, ordinal, text, category="EXPERIENCE"):
    return ResumeEvidenceItem(
        resume_version_id=version_id,
        ordinal=ordinal,
        category=category,
        section_header="Experience",
        bullet_text=text,
    )


def reject(session, callback):
    with pytest.raises(IntegrityError), session.begin_nested():
        callback()
        session.flush()


def test_evidence_constraints_bound_provenance_text_raw_text_and_confidence(evidence_graph):
    session, _, _, skill, version, _ = evidence_graph
    reject(session, lambda: session.add(item(version.id, -1, "Valid")))
    reject(session, lambda: session.add(item(version.id, 0, "   ")))
    reject(session, lambda: session.add(item(version.id, 0, "Valid", category="PROJECT")))

    saved = item(version.id, 0, "Built services with Python")
    session.add(saved)
    session.flush()
    reject(
        session,
        lambda: session.add(
            ResumeEvidenceSkill(
                evidence_item_id=saved.id,
                skill_id=skill.id,
                parser_confidence=1.01,
            )
        ),
    )
    version.raw_extracted_text = "x" * 262_145
    with pytest.raises(IntegrityError), session.begin_nested():
        session.flush()


def test_owner_scoped_version_and_evidence_queries_are_exact_and_ordered(evidence_graph):
    session, owner, other, _, version, _ = evidence_graph
    session.add_all(
        [
            item(version.id, 9, "Later source line"),
            item(version.id, 2, "Earlier source line"),
        ]
    )
    session.flush()
    repository = ResumeRepository(session)

    assert repository.owned_version(owner.id, version.id, lock=True).id == version.id
    assert repository.owned_version(other.id, version.id) is None
    assert [row.ordinal for row in repository.evidence_for_owned_version(owner.id, version.id)] == [
        2,
        9,
    ]
    assert repository.evidence_for_owned_version(other.id, version.id) == []


def test_atomic_replacement_is_version_scoped_and_never_writes_user_skills(evidence_graph):
    session, owner, _, _, version, other_version = evidence_graph
    old = item(version.id, 0, "Old evidence")
    untouched = item(other_version.id, 0, "Other version evidence")
    session.add_all([old, untouched])
    session.flush()
    before_user_skills = list(
        session.scalars(select(UserSkill).where(UserSkill.user_id == owner.id))
    )
    replacement = [
        item(version.id, 0, "First replacement"),
        item(version.id, 1, "Second replacement", category="SKILLS"),
    ]
    repository = ResumeRepository(session)

    with patch.object(session, "commit", side_effect=AssertionError("repository must not commit")):
        repository.replace_evidence_for_version(version.id, replacement)
        session.flush()

    assert [
        row.bullet_text for row in repository.evidence_for_owned_version(owner.id, version.id)
    ] == ["First replacement", "Second replacement"]
    assert [
        row.bullet_text
        for row in session.scalars(
            select(ResumeEvidenceItem).where(
                ResumeEvidenceItem.resume_version_id == other_version.id
            )
        )
    ] == ["Other version evidence"]
    assert (
        list(session.scalars(select(UserSkill).where(UserSkill.user_id == owner.id)))
        == before_user_skills
    )


def test_replacement_rejects_cross_version_items_before_deleting_existing_evidence(evidence_graph):
    session, owner, _, _, version, other_version = evidence_graph
    preserved = item(version.id, 0, "Preserved evidence")
    session.add(preserved)
    session.flush()
    repository = ResumeRepository(session)

    with pytest.raises(ValueError, match="different resume version"):
        repository.replace_evidence_for_version(version.id, [item(other_version.id, 0, "Invalid")])

    assert [
        row.bullet_text for row in repository.evidence_for_owned_version(owner.id, version.id)
    ] == ["Preserved evidence"]
