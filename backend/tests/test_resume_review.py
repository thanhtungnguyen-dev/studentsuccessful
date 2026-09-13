"""Persistent, user-owned review decisions over Phase 16 draft snapshots."""

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.main import app
from backend.app.models.base import Base
from backend.app.models.job import NormalizedJob
from backend.app.models.portfolio import Project
from backend.app.models.resume import Resume, UserSkill
from backend.app.models.resume_review import ResumeTailoringReview, ResumeTailoringReviewItem
from backend.tests.test_jobs import seed_job
from backend.tests.test_skill_gap import (
    account,
    add_project_technology,
    catalog,
    job_requirements,
    resume_versions,
)


def review_url(job_id):
    return f"/api/v1/jobs/{job_id}/resume-reviews"


def csrf(client):
    return {"X-CSRF-Token": client.cookies["ss_csrf"]}


def review_fixture(connection):
    client, owner = account()
    skills = catalog(connection)
    job_id = seed_job(connection, title="Review job", external_id="review-job", posted_at=None)
    job_requirements(connection, job_id, skills)
    resume_id, selected_id, _, _, _ = resume_versions(
        connection, owner, skills["Python"], skills["Terraform"]
    )
    confirmed_id = uuid4()
    connection.execute(
        UserSkill.__table__.insert(),
        {
            "id": confirmed_id,
            "user_id": owner,
            "skill_id": skills["Docker"],
            "source": "USER",
            "confirmed_by_user": True,
        },
    )
    project_id = add_project_technology(connection, owner, skills["AWS"])
    return client, owner, job_id, resume_id, selected_id, confirmed_id, project_id


def create_review(client, job_id, selected_id):
    response = client.post(
        review_url(job_id),
        json={"resume_version_id": str(selected_id)},
        headers=csrf(client),
    )
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def snapshot(connection, names):
    return {
        table.name: list(connection.execute(select(table)).mappings())
        for table in Base.metadata.sorted_tables
        if table.name in names
    }


def test_create_snapshots_phase16_suggestions_for_only_the_owned_selected_version(isolated_database):
    client, owner, job_id, resume_id, selected_id, confirmed_id, project_id = review_fixture(
        isolated_database
    )
    protected = {
        "resumes",
        "resume_versions",
        "resume_evidence_items",
        "resume_evidence_skills",
        "user_skills",
        "projects",
        "normalized_jobs",
    }
    before = snapshot(isolated_database, protected)
    review = create_review(client, job_id, selected_id)
    assert review["status"] == "DRAFT"
    assert review["job_id"] == str(job_id)
    assert review["source_resume_version_id"] == str(selected_id)
    assert review["resume_title"] == "Targeted resume"
    assert review["resume_version_number"] == 1
    assert [item["name"] for item in review["items"]] == ["AWS", "Docker"]
    source_by_name = {item["name"]: item["provenance"] for item in review["items"]}
    assert source_by_name["AWS"][0]["source_type"] == "PROJECT"
    assert source_by_name["AWS"][0]["source_id"] == str(project_id)
    assert source_by_name["Docker"][0]["source_type"] == "CONFIRMED_BY_USER"
    assert source_by_name["Docker"][0]["source_id"] == str(confirmed_id)
    assert all(item["decision"] == "PENDING" for item in review["items"])
    assert all(item["user_edited_text"] is None for item in review["items"])
    assert all(item["action"] == "CONSIDER_ADDING_EXISTING_EVIDENCE" for item in review["items"])
    assert snapshot(isolated_database, protected) == before
    assert (
        isolated_database.execute(select(ResumeTailoringReview.user_id)).scalar_one() == owner
    )
    assert len(isolated_database.execute(select(ResumeTailoringReviewItem)).scalars().all()) == 2
    assert resume_id == isolated_database.execute(select(Resume.id)).scalar_one()


def test_accept_reject_and_user_edit_persist_separately_with_original_provenance(isolated_database):
    client, _, job_id, _, selected_id, _, project_id = review_fixture(isolated_database)
    review = create_review(client, job_id, selected_id)
    items = {item["name"]: item for item in review["items"]}
    docker_original = items["Docker"]["original_draft_text"]
    docker_original_provenance = items["Docker"]["provenance"]
    aws_original_provenance = items["AWS"]["provenance"]
    protected = {
        "resumes",
        "resume_versions",
        "resume_evidence_items",
        "resume_evidence_skills",
        "user_skills",
        "projects",
        "normalized_jobs",
    }
    before_edit = snapshot(isolated_database, protected)

    edited = client.patch(
        f"{review_url(job_id)}/{review['id']}/items/{items['Docker']['id']}",
        json={"user_edited_text": "Docker wording selected by the user."},
        headers=csrf(client),
    )
    assert edited.status_code == 200, edited.text
    accepted = client.patch(
        f"{review_url(job_id)}/{review['id']}/items/{items['Docker']['id']}",
        json={"decision": "ACCEPTED"},
        headers=csrf(client),
    )
    assert accepted.status_code == 200, accepted.text
    rejected = client.patch(
        f"{review_url(job_id)}/{review['id']}/items/{items['AWS']['id']}",
        json={"decision": "REJECTED"},
        headers=csrf(client),
    )
    assert rejected.status_code == 200, rejected.text
    saved = client.get(review_url(job_id), params={"resume_version_id": str(selected_id)})
    assert saved.status_code == 200, saved.text
    persisted = {item["name"]: item for item in saved.json()["items"]}
    assert persisted["Docker"]["decision"] == "ACCEPTED"
    assert persisted["Docker"]["original_draft_text"] == docker_original
    assert persisted["Docker"]["user_edited_text"] == "Docker wording selected by the user."
    assert persisted["Docker"]["provenance"] == docker_original_provenance
    assert persisted["AWS"]["decision"] == "REJECTED"
    assert persisted["AWS"]["provenance"] == aws_original_provenance
    assert snapshot(isolated_database, protected) == before_edit

    isolated_database.execute(
        Project.__table__.update().where(Project.id == project_id).values(title="Changed project")
    )
    isolated_database.execute(
        NormalizedJob.__table__.update()
        .where(NormalizedJob.id == job_id)
        .values(title="Changed job title")
    )
    snapshot_read = client.get(review_url(job_id), params={"resume_version_id": str(selected_id)})
    assert snapshot_read.status_code == 200
    snapshot_items = {item["name"]: item for item in snapshot_read.json()["items"]}
    assert snapshot_read.json()["job_title"] == "Review job"
    assert snapshot_items["AWS"]["provenance"] == aws_original_provenance


def test_finalization_is_immutable_and_never_changes_resume_or_candidate_facts(isolated_database):
    client, _, job_id, _, selected_id, _, _ = review_fixture(isolated_database)
    review = create_review(client, job_id, selected_id)
    protected = {
        "resumes",
        "resume_versions",
        "resume_evidence_items",
        "resume_evidence_skills",
        "user_skills",
        "projects",
        "normalized_jobs",
    }
    before = snapshot(isolated_database, protected)
    for item in review["items"]:
        response = client.patch(
            f"{review_url(job_id)}/{review['id']}/items/{item['id']}",
            json={"decision": "ACCEPTED" if item["name"] == "Docker" else "REJECTED"},
            headers=csrf(client),
        )
        assert response.status_code == 200, response.text
    final = client.post(
        f"{review_url(job_id)}/{review['id']}/finalize", headers=csrf(client)
    )
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "FINALIZED"
    assert final.json()["finalized_at"] is not None
    assert snapshot(isolated_database, protected) == before
    immutable = client.patch(
        f"{review_url(job_id)}/{review['id']}/items/{review['items'][0]['id']}",
        json={"decision": "REJECTED", "user_edited_text": "Attempted late edit"},
        headers=csrf(client),
    )
    assert immutable.status_code == 409
    assert immutable.json()["code"] == "RESUME_TAILORING_REVIEW_FINALIZED"
    repeated = client.post(f"{review_url(job_id)}/{review['id']}/finalize", headers=csrf(client))
    assert repeated.status_code == 200
    assert repeated.json()["id"] == final.json()["id"]
    assert repeated.json()["status"] == "FINALIZED"


def test_review_ownership_csrf_no_store_and_invalid_mutations_are_safe(isolated_database):
    client, _, job_id, _, selected_id, _, _ = review_fixture(isolated_database)
    review = create_review(client, job_id, selected_id)
    other, _ = account()
    item_id = review["items"][0]["id"]
    get_path = review_url(job_id)
    item_path = f"{get_path}/{review['id']}/items/{item_id}"
    finalize_path = f"{get_path}/{review['id']}/finalize"

    cross_user = (
        other.get(get_path, params={"resume_version_id": str(selected_id)}),
        other.post(get_path, json={"resume_version_id": str(selected_id)}, headers=csrf(other)),
        other.patch(item_path, json={"decision": "ACCEPTED"}, headers=csrf(other)),
        other.post(finalize_path, headers=csrf(other)),
    )
    assert [response.status_code for response in cross_user] == [404, 404, 404, 404]
    assert all(response.headers["cache-control"] == "no-store" for response in cross_user)

    no_csrf = (
        client.post(get_path, json={"resume_version_id": str(selected_id)}),
        client.patch(item_path, json={"decision": "ACCEPTED"}),
        client.post(finalize_path),
    )
    assert [response.status_code for response in no_csrf] == [403, 403, 403]
    assert TestClient(app).get(get_path, params={"resume_version_id": str(selected_id)}).status_code == 401
    invalid = (
        client.get(get_path, params={"resume_version_id": str(selected_id), "user_id": str(uuid4())}),
        client.post(get_path, params={"resume_version_id": str(selected_id)}, json={"resume_version_id": str(selected_id)}, headers=csrf(client)),
        client.patch(item_path, json={}, headers=csrf(client)),
        client.patch(item_path, json={"user_edited_text": "   "}, headers=csrf(client)),
    )
    assert [response.status_code for response in invalid] == [422, 422, 422, 422]
    assert all(response.headers["cache-control"] == "no-store" for response in invalid)
