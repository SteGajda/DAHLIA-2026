"""Auth endpoint integration tests — Phase 2.

All tests run against an isolated SQLite in-memory database (via the
``client`` fixture from ``conftest.py``).  No external services required.

Test organisation
-----------------
Each class covers one endpoint or logical group:

* ``TestRegister``          — POST /api/v1/auth/register
* ``TestVerifyEmail``       — POST /api/v1/auth/verify-email
* ``TestLogin``             — POST /api/v1/auth/login
* ``TestRefresh``           — POST /api/v1/auth/refresh
* ``TestLogout``            — POST /api/v1/auth/logout
* ``TestMe``                — GET  /api/v1/auth/me
* ``TestRequestRole``       — POST /api/v1/auth/request-role

Shared helpers
--------------
``_register`` / ``_login`` / ``_auth_headers`` simplify test setup so that
each test focuses on a single behaviour.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_email_verification_token,
    hash_refresh_token,
)
from app.models.user import AppUser, RefreshToken

# Shared helpers

_BASE = "/api/v1/auth"

_VALID_REGISTER = {
    "email": "alice@example.com",
    "password": "securepass1",
    "display_name": "Alice",
    "is_pw_affiliated": False,
    "consent_given": True,
}


def _register(client, data: dict | None = None) -> dict:
    """Register a user and return the JSON response."""
    return client.post(f"{_BASE}/register", json=data or _VALID_REGISTER).json()


def _login(client, email: str = "alice@example.com", password: str = "securepass1") -> dict:
    """Login and return the token response JSON."""
    resp = client.post(f"{_BASE}/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _auth_headers(client) -> dict[str, str]:
    """Register + login, return Authorization header dict."""
    _register(client)
    tokens = _login(client)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# POST /register
class TestRegister:
    def test_success(self, client):
        resp = client.post(f"{_BASE}/register", json=_VALID_REGISTER)
        assert resp.status_code == 201
        body = resp.json()
        assert "user_id" in body
        assert body["user_id"] > 0

    def test_duplicate_email_returns_409(self, client):
        client.post(f"{_BASE}/register", json=_VALID_REGISTER)
        resp = client.post(f"{_BASE}/register", json=_VALID_REGISTER)
        assert resp.status_code == 409

    def test_invalid_email_returns_422(self, client):
        bad = {**_VALID_REGISTER, "email": "not-an-email"}
        resp = client.post(f"{_BASE}/register", json=bad)
        assert resp.status_code == 422

    def test_password_too_short_returns_422(self, client):
        bad = {**_VALID_REGISTER, "password": "short"}
        resp = client.post(f"{_BASE}/register", json=bad)
        assert resp.status_code == 422

    def test_blank_display_name_returns_422(self, client):
        bad = {**_VALID_REGISTER, "display_name": "   "}
        resp = client.post(f"{_BASE}/register", json=bad)
        assert resp.status_code == 422

    def test_affiliated_without_student_id_returns_422(self, client):
        bad = {**_VALID_REGISTER, "is_pw_affiliated": True, "student_id_number": None}
        resp = client.post(f"{_BASE}/register", json=bad)
        assert resp.status_code == 422

    def test_affiliated_with_invalid_student_id_returns_422(self, client):
        bad = {**_VALID_REGISTER, "is_pw_affiliated": True, "student_id_number": "ABC123"}
        resp = client.post(f"{_BASE}/register", json=bad)
        assert resp.status_code == 422

    def test_affiliated_with_valid_student_id_succeeds(self, client):
        data = {**_VALID_REGISTER, "is_pw_affiliated": True, "student_id_number": "123456"}
        resp = client.post(f"{_BASE}/register", json=data)
        assert resp.status_code == 201

    def test_new_user_is_not_email_verified(self, client):
        _register(client)
        headers = _auth_headers.__wrapped__(client) if hasattr(_auth_headers, "__wrapped__") else None
        # Verify via /me endpoint
        tokens = _login(client)
        me = client.get(f"{_BASE}/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert me.json()["is_email_verified"] is False

    def test_new_user_has_USER_role(self, client):
        _register(client)
        tokens = _login(client)
        assert tokens["role_code"] == "USER"


# POST /verify-email
class TestVerifyEmail:
    def test_success(self, client, sqlite_session):
        _register(client)
        user = sqlite_session.query(AppUser).filter_by(email="alice@example.com").first()
        token = create_email_verification_token(user.user_id)

        resp = client.post(f"{_BASE}/verify-email", json={"token": token})
        assert resp.status_code == 200
        assert "verified" in resp.json()["message"].lower()

        sqlite_session.refresh(user)
        assert user.is_email_verified is True

    def test_already_verified_is_idempotent(self, client, sqlite_session):
        _register(client)
        user = sqlite_session.query(AppUser).filter_by(email="alice@example.com").first()
        token = create_email_verification_token(user.user_id)

        client.post(f"{_BASE}/verify-email", json={"token": token})
        resp = client.post(f"{_BASE}/verify-email", json={"token": token})
        assert resp.status_code == 200
        assert "already" in resp.json()["message"].lower()

    def test_invalid_token_returns_400(self, client):
        resp = client.post(f"{_BASE}/verify-email", json={"token": "not.a.jwt"})
        assert resp.status_code == 400

    def test_wrong_purpose_token_returns_400(self, client, sqlite_session):
        _register(client)
        user = sqlite_session.query(AppUser).filter_by(email="alice@example.com").first()
        # Use an access token (type="access") instead of a verify token
        access_token = create_access_token(user.user_id, "USER")
        resp = client.post(f"{_BASE}/verify-email", json={"token": access_token})
        assert resp.status_code == 400

    def test_expired_token_returns_400(self, client, sqlite_session):
        _register(client)
        user = sqlite_session.query(AppUser).filter_by(email="alice@example.com").first()
        settings = get_settings()
        # Craft a token with exp already in the past
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        payload = {
            "sub": str(user.user_id),
            "purpose": "email_verify",
            "iat": past - timedelta(hours=25),
            "exp": past,
        }
        expired_token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        resp = client.post(f"{_BASE}/verify-email", json={"token": expired_token})
        assert resp.status_code == 400


# POST /login
class TestLogin:
    def test_success_returns_tokens(self, client):
        _register(client)
        resp = client.post(f"{_BASE}/login", json={"email": "alice@example.com", "password": "securepass1"})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        assert body["role_code"] == "USER"

    def test_wrong_password_returns_401(self, client):
        _register(client)
        resp = client.post(f"{_BASE}/login", json={"email": "alice@example.com", "password": "wrongpassword"})
        assert resp.status_code == 401

    def test_nonexistent_email_returns_401(self, client):
        resp = client.post(f"{_BASE}/login", json={"email": "ghost@example.com", "password": "whatever"})
        assert resp.status_code == 401

    def test_access_token_is_valid_jwt(self, client):
        _register(client)
        tokens = _login(client)
        settings = get_settings()
        payload = jwt.decode(tokens["access_token"], settings.SECRET_KEY, algorithms=["HS256"])
        assert payload["type"] == "access"
        assert payload["role_code"] == "USER"

    def test_refresh_token_stored_in_db(self, client, sqlite_session):
        _register(client)
        tokens = _login(client)
        token_hash = hash_refresh_token(tokens["refresh_token"])
        record = sqlite_session.query(RefreshToken).filter_by(token_hash=token_hash).first()
        assert record is not None
        assert record.revoked is False


# POST /refresh
class TestRefresh:
    def test_success_returns_new_access_token(self, client):
        _register(client)
        tokens = _login(client)
        resp = client.post(f"{_BASE}/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        # New token should be a valid JWT
        settings = get_settings()
        payload = jwt.decode(body["access_token"], settings.SECRET_KEY, algorithms=["HS256"])
        assert payload["type"] == "access"

    def test_invalid_refresh_token_returns_401(self, client):
        resp = client.post(f"{_BASE}/refresh", json={"refresh_token": "completely-fake-token"})
        assert resp.status_code == 401

    def test_revoked_refresh_token_returns_401(self, client, sqlite_session):
        _register(client)
        tokens = _login(client)
        # Revoke manually in DB
        token_hash = hash_refresh_token(tokens["refresh_token"])
        record = sqlite_session.query(RefreshToken).filter_by(token_hash=token_hash).first()
        record.revoked = True
        sqlite_session.commit()

        resp = client.post(f"{_BASE}/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert resp.status_code == 401

    def test_expired_refresh_token_returns_401(self, client, sqlite_session):
        _register(client)
        tokens = _login(client)
        # Expire token manually in DB
        token_hash = hash_refresh_token(tokens["refresh_token"])
        record = sqlite_session.query(RefreshToken).filter_by(token_hash=token_hash).first()
        record.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        sqlite_session.commit()

        resp = client.post(f"{_BASE}/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert resp.status_code == 401


# POST /logout
class TestLogout:
    def test_success_revokes_token(self, client, sqlite_session):
        _register(client)
        tokens = _login(client)
        resp = client.post(f"{_BASE}/logout", json={"refresh_token": tokens["refresh_token"]})
        assert resp.status_code == 200

        token_hash = hash_refresh_token(tokens["refresh_token"])
        record = sqlite_session.query(RefreshToken).filter_by(token_hash=token_hash).first()
        assert record.revoked is True

    def test_logout_token_can_no_longer_refresh(self, client):
        _register(client)
        tokens = _login(client)
        client.post(f"{_BASE}/logout", json={"refresh_token": tokens["refresh_token"]})

        resp = client.post(f"{_BASE}/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert resp.status_code == 401

    def test_logout_nonexistent_token_returns_200(self, client):
        """Logout with unknown token must not leak token-existence information."""
        resp = client.post(f"{_BASE}/logout", json={"refresh_token": "unknown-token-xyz"})
        assert resp.status_code == 200


# GET /me
class TestMe:
    def test_success_returns_user_profile(self, client):
        headers = _auth_headers(client)
        resp = client.get(f"{_BASE}/me", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "alice@example.com"
        assert body["display_name"] == "Alice"
        assert body["role_code"] == "USER"

    def test_no_token_returns_401(self, client):
        # FastAPI HTTPBearer returns 403 normally but depending on setup can be 401
        resp = client.get(f"{_BASE}/me")
        assert resp.status_code == 403 or resp.status_code == 401

    def test_invalid_token_returns_401(self, client):
        resp = client.get(f"{_BASE}/me", headers={"Authorization": "Bearer not.a.real.token"})
        assert resp.status_code == 401

    def test_expired_access_token_returns_401(self, client):
        _register(client)
        settings = get_settings()
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        payload = {
            "sub": "1",
            "role_code": "USER",
            "type": "access",
            "iat": past - timedelta(hours=1),
            "exp": past,
        }
        expired_token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        resp = client.get(f"{_BASE}/me", headers={"Authorization": f"Bearer {expired_token}"})
        assert resp.status_code == 401


# POST /request-role
class TestRequestRole:
    def test_user_can_request_user_plus(self, client):
        headers = _auth_headers(client)
        resp = client.post(f"{_BASE}/request-role", json={"requested_role": "USER_PLUS"}, headers=headers)
        assert resp.status_code == 201
        assert resp.json()["request_id"] > 0

    def test_user_can_request_researcher(self, client):
        headers = _auth_headers(client)
        resp = client.post(f"{_BASE}/request-role", json={"requested_role": "RESEARCHER"}, headers=headers)
        assert resp.status_code == 201

    def test_cannot_request_developer_role_returns_422(self, client):
        headers = _auth_headers(client)
        resp = client.post(f"{_BASE}/request-role", json={"requested_role": "DEVELOPER"}, headers=headers)
        assert resp.status_code == 422

    def test_cannot_request_same_role_returns_422(self, client, sqlite_session):
        headers = _auth_headers(client)
        # Manually set user to USER_PLUS
        user = sqlite_session.query(AppUser).filter_by(email="alice@example.com").first()
        user.role_code = "USER_PLUS"
        sqlite_session.commit()
        # Re-login to get token with updated role
        tokens = _login(client)
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        resp = client.post(f"{_BASE}/request-role", json={"requested_role": "USER_PLUS"}, headers=headers)
        assert resp.status_code == 422

    def test_duplicate_pending_request_returns_409(self, client):
        headers = _auth_headers(client)
        client.post(f"{_BASE}/request-role", json={"requested_role": "USER_PLUS"}, headers=headers)
        resp = client.post(f"{_BASE}/request-role", json={"requested_role": "USER_PLUS"}, headers=headers)
        assert resp.status_code == 409

    def test_unauthenticated_returns_401(self, client):
        resp = client.post(f"{_BASE}/request-role", json={"requested_role": "USER_PLUS"})
        assert resp.status_code == 403 or resp.status_code == 401

    def test_invalid_role_string_returns_422(self, client):
        headers = _auth_headers(client)
        resp = client.post(f"{_BASE}/request-role", json={"requested_role": "SUPERADMIN"}, headers=headers)
        assert resp.status_code == 422


class TestForgotPassword:
    def test_existing_user_returns_200(self, client, sqlite_session):
        _register(client, data={**_VALID_REGISTER, "email": "bob@example.com"})
        resp = client.post(f"{_BASE}/forgot-password", json={"email": "bob@example.com"})
        assert resp.status_code == 200
        assert "password reset link has been sent" in resp.json()["message"]

    def test_nonexistent_user_returns_200(self, client):
        resp = client.post(f"{_BASE}/forgot-password", json={"email": "nobody@example.com"})
        assert resp.status_code == 200
        assert "password reset link has been sent" in resp.json()["message"]


class TestResetPassword:
    def test_success(self, client, sqlite_session):
        _register(client, data={**_VALID_REGISTER, "email": "reset@example.com"})
        user = sqlite_session.query(AppUser).filter_by(email="reset@example.com").first()
        from app.core.security import create_password_reset_token, verify_password
        token = create_password_reset_token(user.user_id)

        resp = client.post(f"{_BASE}/reset-password", json={"token": token, "new_password": "new_secure_password"})
        assert resp.status_code == 200
        assert resp.json()["message"] == "Password has been successfully reset."

        sqlite_session.refresh(user)
        assert verify_password("new_secure_password", user.password_hash)

    def test_invalid_token_returns_400(self, client):
        resp = client.post(f"{_BASE}/reset-password", json={"token": "invalid", "new_password": "new_secure_password"})
        assert resp.status_code == 400

    def test_wrong_purpose_token_returns_400(self, client, sqlite_session):
        _register(client, data={**_VALID_REGISTER, "email": "wrong@example.com"})
        user = sqlite_session.query(AppUser).filter_by(email="wrong@example.com").first()
        from app.core.security import create_email_verification_token
        token = create_email_verification_token(user.user_id)

        resp = client.post(f"{_BASE}/reset-password", json={"token": token, "new_password": "new_secure_password"})
        assert resp.status_code == 400

    def test_password_too_short_returns_422(self, client, sqlite_session):
        _register(client, data={**_VALID_REGISTER, "email": "short@example.com"})
        user = sqlite_session.query(AppUser).filter_by(email="short@example.com").first()
        from app.core.security import create_password_reset_token
        token = create_password_reset_token(user.user_id)

        resp = client.post(f"{_BASE}/reset-password", json={"token": token, "new_password": "short"})
        assert resp.status_code == 422
