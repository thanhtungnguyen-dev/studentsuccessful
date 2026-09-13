"""Security regressions against the real auth endpoints and PostgreSQL sessions."""

from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from backend.app.api.deps import CSRF_COOKIE_NAME, session_cookie_name
from backend.app.core import security
from backend.app.core.config import settings
from backend.app.core.unit_of_work import UnitOfWork
from backend.app.main import app
from backend.app.models.user import User, UserSession

PASSWORD = "SecurePassword123!"


@pytest.fixture
def browser():
    with TestClient(app) as client:
        yield client


def register(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"{uuid4()}@example.edu", "password": PASSWORD},
        headers={"Origin": settings.FRONTEND_ORIGIN},
    )
    assert response.status_code == 201
    return response


def cookie_attributes(response):
    cookies = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        cookies.load(header)
    return cookies


def snapshot(user_id):
    with UnitOfWork() as uow:
        session = uow.session.query(UserSession).filter_by(user_id=UUID(user_id)).one()
        return {
            name: getattr(session, name)
            for name in (
                "id",
                "session_token_hash",
                "csrf_token_hash",
                "last_seen_at",
                "expires_at",
                "revoked_at",
            )
        }


@pytest.mark.parametrize(
    "mode,secure,base_url,session_name",
    [
        ("development", False, "http://testserver", "ss_session"),
        ("production", True, "https://students.example", "__Host-ss_session"),
    ],
)
def test_cookie_issuance_and_matching_deletion(monkeypatch, mode, secure, base_url, session_name):
    monkeypatch.setattr(settings, "APP_ENV", mode)
    monkeypatch.setattr(settings, "SESSION_COOKIE_SECURE", secure)
    monkeypatch.setattr(settings, "SESSION_COOKIE_NAME", "__Host-ss_session")
    monkeypatch.setattr(settings, "FRONTEND_ORIGIN", base_url)
    with TestClient(app, base_url=base_url) as client:
        response = register(client)
        issued = cookie_attributes(response)
        assert set(issued) == {session_name, CSRF_COOKIE_NAME}
        for name in issued:
            cookie = issued[name]
            assert bool(cookie["secure"]) is secure
            assert cookie["path"] == "/" and cookie["domain"] == ""
            assert cookie["samesite"].lower() == "lax"
            assert bool(cookie["httponly"]) is (name == session_name)
            assert int(cookie["max-age"]) == settings.SESSION_EXPIRE_DAYS * 86400
            assert len(cookie.value) == 64
        assert issued[CSRF_COOKIE_NAME].value == response.json()["csrf_token"]
        assert issued[session_name].value not in response.text
        logout = client.post(
            "/api/v1/auth/logout", headers={"X-CSRF-Token": issued[CSRF_COOKIE_NAME].value}
        )
        assert logout.status_code == 200
        deleted = cookie_attributes(logout)
        assert set(deleted) == set(issued)
        for name in deleted:
            assert deleted[name]["max-age"] == "0"
            for attribute in ["path", "domain", "secure", "httponly", "samesite"]:
                assert deleted[name][attribute] == issued[name][attribute]
        assert session_name not in client.cookies and CSRF_COOKIE_NAME not in client.cookies
        assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("token", [None, "", "incorrect-token"])
def test_logout_rejects_missing_or_wrong_csrf_without_revocation(browser, token):
    registration = register(browser)
    headers = {} if token is None else {"X-CSRF-Token": token}
    response = browser.post("/api/v1/auth/logout", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_TOKEN_INVALID"
    assert not response.headers.get_list("set-cookie")
    assert snapshot(registration.json()["user"]["id"])["revoked_at"] is None
    assert browser.get("/api/v1/auth/me").status_code == 200


@pytest.mark.parametrize(
    "state,code",
    [
        ("missing", "UNAUTHENTICATED"),
        ("tampered", "UNAUTHENTICATED"),
        ("expired", "SESSION_EXPIRED"),
        ("revoked", "SESSION_REVOKED"),
        ("inactive", "UNAUTHENTICATED"),
    ],
)
def test_me_and_logout_reject_invalid_sessions(browser, state, code):
    registration = register(browser)
    csrf = browser.cookies[CSRF_COOKIE_NAME]
    user_id = UUID(registration.json()["user"]["id"])
    if state in {"missing", "tampered"}:
        browser.cookies.clear()
        if state == "tampered":
            browser.cookies.set(session_cookie_name(), "f" * 64)
    else:
        with UnitOfWork() as uow:
            session = uow.session.query(UserSession).filter_by(user_id=user_id).one()
            if state == "expired":
                session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            elif state == "revoked":
                session.revoked_at = datetime.now(timezone.utc)
            else:
                uow.session.get(User, user_id).is_active = False
            uow.commit()
    for method, path in [("GET", "/api/v1/auth/me"), ("POST", "/api/v1/auth/logout")]:
        response = browser.request(method, path, headers={"X-CSRF-Token": csrf})
        assert response.status_code == 401
        assert response.json()["code"] == code
        assert response.headers["cache-control"] == "no-store"


def test_production_does_not_accept_development_cookie(browser, monkeypatch):
    registration = register(browser)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "SESSION_COOKIE_SECURE", True)
    response = browser.get("/api/v1/auth/me")
    assert registration.cookies.get("ss_session")
    assert response.status_code == 401


@pytest.mark.parametrize("logout_tab", [0, 1])
def test_two_tabs_share_one_stable_session_and_csrf(
    browser, logout_tab, monkeypatch, isolated_database
):
    registration = register(browser)
    user_id = registration.json()["user"]["id"]
    raw_csrf = registration.cookies[CSRF_COOKIE_NAME]
    raw_session = registration.cookies[session_cookie_name()]
    before = snapshot(user_id)
    assert before["csrf_token_hash"] == security.hash_token(raw_csrf)
    assert before["csrf_token_hash"] != raw_csrf
    assert before["session_token_hash"] == security.hash_token(raw_session)
    assert before["session_token_hash"] != raw_session
    commits = Mock(side_effect=AssertionError("Authentication read attempted commit"))
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(isolated_database, "before_cursor_execute", capture)
    try:
        with TestClient(app) as tab_a, TestClient(app) as tab_b:
            tabs = [tab_a, tab_b]
            for tab in tabs:
                tab.cookies.update(registration.cookies)
            with monkeypatch.context() as guard:
                guard.setattr(UnitOfWork, "commit", commits)
                for _ in range(2):
                    for tab in tabs:
                        response = tab.get("/api/v1/auth/me")
                        assert response.status_code == 200
                        assert response.headers["cache-control"] == "no-store"
                        assert not response.headers.get_list("set-cookie")
                        assert tab.cookies[CSRF_COOKIE_NAME] == raw_csrf
            assert snapshot(user_id) == before
            assert not any(
                s.lstrip().upper().startswith(("UPDATE ", "INSERT ", "DELETE ")) for s in statements
            )
            commits.assert_not_called()
            # Either tab can use the original token; logout then invalidates both.
            response = tabs[logout_tab].post(
                "/api/v1/auth/logout", headers={"X-CSRF-Token": raw_csrf}
            )
            assert response.status_code == 200
            assert snapshot(user_id)["revoked_at"] is not None
            assert tabs[1 - logout_tab].get("/api/v1/auth/me").status_code == 401
    finally:
        event.remove(isolated_database, "before_cursor_execute", capture)


def test_login_creates_independent_session_and_csrf_pair(browser):
    first = register(browser)
    old_session = first.cookies[session_cookie_name()]
    old_csrf = first.cookies[CSRF_COOKIE_NAME]
    response = browser.post(
        "/api/v1/auth/login",
        json={"email": first.json()["user"]["email"], "password": PASSWORD},
        headers={"Origin": settings.FRONTEND_ORIGIN},
    )
    assert response.status_code == 200
    assert response.cookies[session_cookie_name()] != old_session
    assert response.cookies[CSRF_COOKIE_NAME] != old_csrf
    with UnitOfWork() as uow:
        sessions = (
            uow.session.query(UserSession).filter_by(user_id=UUID(first.json()["user"]["id"])).all()
        )
        assert len(sessions) == 2
        assert {s.csrf_token_hash for s in sessions} == {
            security.hash_token(old_csrf),
            security.hash_token(response.cookies[CSRF_COOKIE_NAME]),
        }
        assert all(s.revoked_at is None for s in sessions)
    wrong_pair = browser.post("/api/v1/auth/logout", headers={"X-CSRF-Token": old_csrf})
    assert wrong_pair.status_code == 403
    valid_pair = browser.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": response.cookies[CSRF_COOKIE_NAME]}
    )
    assert valid_pair.status_code == 200


@pytest.mark.parametrize("route", ["register", "login"])
@pytest.mark.parametrize(
    "origin", ["https://foreign.example", "null", "https://students.example.evil", None]
)
def test_production_auth_mutations_reject_untrusted_origin(
    monkeypatch, route, origin, isolated_database
):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "SESSION_COOKIE_SECURE", True)
    monkeypatch.setattr(settings, "FRONTEND_ORIGIN", "https://students.example")
    # No DB access should occur when Origin validation rejects the request.
    with monkeypatch.context() as guard:
        guard.setattr(
            UnitOfWork,
            "__enter__",
            Mock(side_effect=AssertionError("DB opened for rejected Origin")),
        )
        with TestClient(app, base_url="https://students.example") as client:
            headers = {} if origin is None else {"Origin": origin}
            response = client.post(
                "/api/v1/auth/" + route,
                json={"email": "person@example.edu", "password": PASSWORD},
                headers=headers,
            )
    assert response.status_code == 403
    assert response.json()["code"] == "AUTH_ORIGIN_REJECTED"
    assert response.headers["cache-control"] == "no-store"


def test_production_allowed_origin_and_next_rewrite_origin(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "SESSION_COOKIE_SECURE", True)
    monkeypatch.setattr(settings, "FRONTEND_ORIGIN", "https://students.example")
    # The proxy's internal Host differs from the original browser Origin.
    with TestClient(app, base_url="https://backend.internal") as client:
        registration = register(client)
        response = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "https://students.example"},
            json={"email": registration.json()["user"]["email"], "password": PASSWORD},
        )
        assert response.status_code == 200


@pytest.mark.parametrize("route", ["register", "login"])
def test_foreign_origin_rejected_in_development(browser, route):
    response = browser.post(
        "/api/v1/auth/" + route,
        headers={"Origin": "https://foreign.example"},
        json={"email": "person@example.edu", "password": PASSWORD},
    )
    assert response.status_code == 403


def test_duplicate_origin_rejected(browser):
    response = browser.post(
        "/api/v1/auth/register",
        headers=[("Origin", settings.FRONTEND_ORIGIN), ("Origin", settings.FRONTEND_ORIGIN)],
        json={"email": "person@example.edu", "password": PASSWORD},
    )
    assert response.status_code == 403


def test_removed_csrf_endpoint_is_absent_and_cannot_rotate(browser):
    registration = register(browser)
    before = snapshot(registration.json()["user"]["id"])
    response = browser.get("/api/v1/auth/csrf")
    assert response.status_code == 404
    assert "/api/v1/auth/csrf" not in app.openapi()["paths"]
    assert "CsrfResponse" not in app.openapi()["components"]["schemas"]
    assert snapshot(registration.json()["user"]["id"]) == before


def test_auth_success_and_validation_errors_are_not_cacheable(browser):
    response = register(browser)
    assert response.headers["cache-control"] == "no-store"
    response = browser.post(
        "/api/v1/auth/login", json={"email": "unknown@example.edu", "password": PASSWORD}
    )
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    response = browser.post("/api/v1/auth/register", json={})
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    response = browser.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": browser.cookies[CSRF_COOKIE_NAME]}
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "cache-control" not in browser.get("/health/live").headers


def test_csrf_validation_uses_constant_time_digest_comparison(browser, monkeypatch):
    registration = register(browser)
    token = registration.cookies[CSRF_COOKIE_NAME]
    original = security.hmac.compare_digest
    compare = Mock(wraps=original)
    monkeypatch.setattr(security.hmac, "compare_digest", compare)
    response = browser.post("/api/v1/auth/logout", headers={"X-CSRF-Token": token})
    assert response.status_code == 200
    compare.assert_called_once_with(security.hash_token(token), security.hash_token(token))
