"""Comprehensive test suite for Phase 6A Authentication Minimum and CSRF protection."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.core.security import hash_token
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.main import app
from backend.app.models.base import generate_uuid
from backend.app.models.user import User, UserSession

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_cookies():
    client.cookies.clear()
    yield
    client.cookies.clear()


def test_register_valid_user_and_session_cookie():
    """Register creates an account, hashes password, sets session cookie, and returns CSRF token."""
    raw_email = f"  Student_{str(generate_uuid())[:8]}@University.EDU  "
    password = "StrongPassword123!"

    response = client.post(
        "/api/v1/auth/register",
        json={"email": raw_email, "password": password},
    )

    assert response.status_code == 201
    data = response.json()
    assert "user" in data
    assert "csrf_token" in data
    assert data["user"]["email"] == raw_email.strip().lower()
    assert len(data["csrf_token"]) == 64  # 256-bit hex

    # Verify cookie was set
    cookie_header = response.headers.get("set-cookie")
    assert cookie_header is not None
    assert "ss_session" in cookie_header or settings.SESSION_COOKIE_NAME in cookie_header
    assert "HttpOnly" in cookie_header
    assert "samesite=lax" in cookie_header.lower()

    # Verify DB: password is Argon2 hash, not plaintext
    with UnitOfWork() as uow:
        db_user = uow.session.query(User).filter_by(id=UUID(data["user"]["id"])).first()
        assert db_user is not None
        assert db_user.password_hash != password
        assert db_user.password_hash.startswith("$argon2id$")

        # Verify session token in DB is stored as SHA-256 hash, not raw token
        cookie_val = response.cookies.get(settings.SESSION_COOKIE_NAME) or response.cookies.get(
            "ss_session"
        )
        assert cookie_val is not None
        session = uow.session.query(UserSession).filter_by(user_id=db_user.id).first()
        assert session is not None
        assert session.session_token_hash == hash_token(cookie_val)
        assert session.session_token_hash != cookie_val
        # Verify csrf_token_hash in DB is SHA-256 of the returned csrf_token
        assert session.csrf_token_hash == hash_token(data["csrf_token"])


def test_register_duplicate_email_rejected():
    """Duplicate email registration is rejected with 409 Conflict."""
    email = f"dup_{str(generate_uuid())[:8]}@test.edu"
    password = "Password123!"

    resp1 = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert resp1.status_code == 201

    # Attempt registration with different casing
    resp2 = client.post(
        "/api/v1/auth/register",
        json={"email": email.upper(), "password": "DifferentPassword123!"},
    )
    assert resp2.status_code == 409
    assert resp2.json()["code"] == "EMAIL_ALREADY_REGISTERED"


def test_login_success():
    """Login succeeds with valid credentials and returns fresh session and CSRF token."""
    email = f"login_{str(generate_uuid())[:8]}@test.edu"
    password = "CorrectPassword123!"

    reg_resp = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert reg_resp.status_code == 201

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email.upper(), "password": password},
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert data["user"]["email"] == email.lower()
    assert "csrf_token" in data


def test_login_invalid_credentials_generic_response():
    """Invalid email and invalid password both return identical generic 401 INVALID_CREDENTIALS."""
    email = f"exist_{str(generate_uuid())[:8]}@test.edu"
    password = "ValidPassword123!"

    client.post("/api/v1/auth/register", json={"email": email, "password": password})

    # 1. Non-existent email
    resp_nonexistent = client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@test.edu", "password": password},
    )
    assert resp_nonexistent.status_code == 401
    assert resp_nonexistent.json()["code"] == "INVALID_CREDENTIALS"

    # 2. Existing email with incorrect password
    resp_wrong_pw = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword999!"},
    )
    assert resp_wrong_pw.status_code == 401
    assert resp_wrong_pw.json()["code"] == "INVALID_CREDENTIALS"

    # Ensure responses are identical to prevent account enumeration
    assert resp_nonexistent.json()["detail"] == resp_wrong_pw.json()["detail"]


def test_get_current_user_me_authenticated():
    """GET /auth/me returns current user profile when session cookie is provided."""
    email = f"me_{str(generate_uuid())[:8]}@test.edu"
    password = "MyPassword123!"

    reg_resp = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    cookies = reg_resp.cookies

    me_resp = client.get("/api/v1/auth/me", cookies=cookies)
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == email.lower()


def test_get_current_user_me_unauthenticated():
    """GET /auth/me returns 401 UNAUTHENTICATED when no cookie is sent."""
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHENTICATED"


def test_get_current_user_me_rejects_expired_session():
    """GET /auth/me rejects expired session with 401 SESSION_EXPIRED."""
    email = f"expired_{str(generate_uuid())[:8]}@test.edu"
    password = "MyPassword123!"

    reg_resp = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    cookies = reg_resp.cookies
    user_id = UUID(reg_resp.json()["user"]["id"])

    # Manually expire the session in the database
    with UnitOfWork() as uow:
        session = uow.session.query(UserSession).filter_by(user_id=user_id).first()
        session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        uow.commit()

    resp = client.get("/api/v1/auth/me", cookies=cookies)
    assert resp.status_code == 401
    assert resp.json()["code"] == "SESSION_EXPIRED"


def test_get_current_user_me_rejects_revoked_session():
    """GET /auth/me rejects explicitly revoked session with 401 SESSION_REVOKED."""
    email = f"revoked_{str(generate_uuid())[:8]}@test.edu"
    password = "MyPassword123!"

    reg_resp = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    cookies = reg_resp.cookies
    user_id = UUID(reg_resp.json()["user"]["id"])

    # Manually revoke the session in the database
    with UnitOfWork() as uow:
        session = uow.session.query(UserSession).filter_by(user_id=user_id).first()
        session.revoked_at = datetime.now(timezone.utc)
        uow.commit()

    resp = client.get("/api/v1/auth/me", cookies=cookies)
    assert resp.status_code == 401
    assert resp.json()["code"] == "SESSION_REVOKED"


def test_logout_revokes_session_and_clears_cookie():
    """POST /auth/logout marks session revoked in database and clears session cookie."""
    email = f"logout_{str(generate_uuid())[:8]}@test.edu"
    password = "MyPassword123!"

    reg_resp = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    cookies = reg_resp.cookies
    user_id = UUID(reg_resp.json()["user"]["id"])

    logout_resp = client.post(
        "/api/v1/auth/logout",
        cookies=cookies,
        headers={"X-CSRF-Token": reg_resp.cookies["ss_csrf"]},
    )
    assert logout_resp.status_code == 200

    # Verify session is revoked in DB
    with UnitOfWork() as uow:
        session = uow.session.query(UserSession).filter_by(user_id=user_id).first()
        assert session.revoked_at is not None

    # Subsequent /auth/me request is rejected
    me_resp = client.get("/api/v1/auth/me", cookies=cookies)
    assert me_resp.status_code == 401


def test_cross_user_isolation():
    """One user cannot access another user's identity."""
    user1_email = f"user1_{str(generate_uuid())[:8]}@test.edu"
    user2_email = f"user2_{str(generate_uuid())[:8]}@test.edu"
    pw = "StrongPass123!"

    resp1 = client.post("/api/v1/auth/register", json={"email": user1_email, "password": pw})
    resp2 = client.post("/api/v1/auth/register", json={"email": user2_email, "password": pw})

    cookies1 = resp1.cookies
    cookies2 = resp2.cookies

    me1 = client.get("/api/v1/auth/me", cookies=cookies1).json()
    me2 = client.get("/api/v1/auth/me", cookies=cookies2).json()

    assert me1["email"] == user1_email.lower()
    assert me2["email"] == user2_email.lower()
    assert me1["id"] != me2["id"]


def test_concurrent_registration_returns_one_created_and_one_conflict(database_engine, monkeypatch):
    """Both requests pass the pre-check; the unique index decides the winner."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import delete, select
    from sqlalchemy.orm import sessionmaker

    from backend.app.api.deps import get_uow
    from backend.app.services import auth as auth_module

    email = f"race_{generate_uuid()}@example.edu"
    barrier = Barrier(2)
    original_hash = auth_module.hash_password
    factory = sessionmaker(bind=database_engine)

    def synchronized_hash(password):
        result = original_hash(password)
        barrier.wait(timeout=10)
        return result

    def independent_uow():
        with UnitOfWork(factory) as uow:
            yield uow

    def register():
        with TestClient(app) as thread_client:
            response = thread_client.post(
                "/api/v1/auth/register", json={"email": email, "password": "ConcurrentPassword123!"}
            )
            return response.status_code, response.json()

    monkeypatch.setattr(auth_module, "hash_password", synchronized_hash)
    app.dependency_overrides[get_uow] = independent_uow
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: register(), range(2)))
        assert sorted(status for status, _ in results) == [201, 409]
        assert (
            next(body for status, body in results if status == 409)["code"]
            == "EMAIL_ALREADY_REGISTERED"
        )
        with database_engine.connect() as connection:
            assert len(connection.execute(select(User.id).where(User.email == email)).all()) == 1
    finally:
        app.dependency_overrides.pop(get_uow, None)
        # This one test needs independent commits; remove only its unique account.
        with database_engine.begin() as connection:
            connection.execute(delete(User).where(User.email == email))
