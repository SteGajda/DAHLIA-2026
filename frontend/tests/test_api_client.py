"""Unit tests for ApiClient using isolated HTTP mock transport."""

import asyncio
import json
import pytest
import httpx
import jwt

from dahlia.core.api_client import ApiClient, ApiResult


class MockKeyring:
    """In-memory keyring stand-in for isolated testing."""

    def __init__(self):
        self.passwords = {}

    def set_password(self, service, username, password):
        self.passwords[(service, username)] = password

    def get_password(self, service, username):
        return self.passwords.get((service, username))

    def delete_password(self, service, username):
        self.passwords.pop((service, username), None)


@pytest.fixture
def mock_keyring(monkeypatch):
    store = MockKeyring()
    monkeypatch.setattr("keyring.set_password", store.set_password)
    monkeypatch.setattr("keyring.get_password", store.get_password)
    monkeypatch.setattr("keyring.delete_password", store.delete_password)
    return store


def test_api_client_offline_handling():
    """Verify that when server is unreachable, ApiClient returns is_offline=True."""
    async def _test():
        # Connect to an unroutable port to verify graceful offline handling
        client = ApiClient(base_url="http://127.0.0.1:59999", timeout=0.5)

        health_res = await client.check_health()
        assert not health_res.success
        assert health_res.is_offline
        assert "offline" in health_res.error.lower()

        login_res = await client.login("test@example.com", "secret123")
        assert not login_res.success
        assert login_res.is_offline
        assert "offline" in login_res.error.lower()

    asyncio.run(_test())


def test_api_client_token_storage(mock_keyring):
    """Verify saving, getting, and clearing refresh token via keyring."""
    client = ApiClient()
    assert client.get_refresh_token() is None

    assert client.save_refresh_token("my_refresh_token")
    assert client.get_refresh_token() == "my_refresh_token"

    client.access_token = "some_access_token"
    client.clear_session()
    assert client.access_token is None
    assert client.get_refresh_token() is None


def test_decode_token_payload():
    """Verify decoding payload from token without signature verification."""
    import jwt

    secret_key = "a" * 32
    token = jwt.encode({"sub": "42", "role_code": "RESEARCHER"}, secret_key, algorithm="HS256")
    claims = ApiClient.decode_token_payload(token)
    assert claims is not None
    assert claims["sub"] == "42"
    assert claims["role_code"] == "RESEARCHER"

    client = ApiClient()
    client.access_token = token
    assert client.get_current_role() == "RESEARCHER"


def test_full_auth_flow_mock_transport(mock_keyring):
    """Test full registration, login, profile, auto-login, and logout flow using MockTransport.

    Completely isolated from the backend package — no cross-project imports.
    """
    secret_key = "a" * 32
    valid_access_token = jwt.encode({"sub": "1", "role_code": "USER"}, secret_key, algorithm="HS256")
    new_access_token = jwt.encode({"sub": "1", "role_code": "RESEARCHER"}, secret_key, algorithm="HS256")

    def mock_backend_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content.decode("utf-8")) if request.content else {}

        if path == "/health":
            return httpx.Response(200, json={"status": "ok"})

        if path == "/api/v1/auth/register":
            if "@" in body.get("email", ""):
                return httpx.Response(201, json={"message": "Account created", "user_id": 1})
            return httpx.Response(422, json={"detail": "Invalid email"})

        if path == "/api/v1/auth/login":
            if body.get("password") == "SecurePassword123!":
                return httpx.Response(
                    200,
                    json={
                        "access_token": valid_access_token,
                        "refresh_token": "valid_refresh_token_123",
                        "token_type": "bearer",
                        "role_code": "USER",
                    },
                )
            return httpx.Response(401, json={"detail": "Incorrect e-mail or password."})

        if path == "/api/v1/auth/me":
            auth_header = request.headers.get("Authorization")
            if auth_header in (f"Bearer {valid_access_token}", f"Bearer {new_access_token}"):
                return httpx.Response(
                    200,
                    json={
                        "user_id": 1,
                        "email": "tester@pw.edu.pl",
                        "display_name": "Tester",
                        "role_code": "USER",
                        "is_email_verified": True,
                        "is_pw_affiliated": True,
                        "consent_given": True,
                        "created_at": "2026-01-01T00:00:00Z",
                    },
                )
            return httpx.Response(401, json={"detail": "Unauthorized"})

        if path == "/api/v1/auth/request-role":
            if request.headers.get("Authorization"):
                return httpx.Response(
                    201,
                    json={"message": "Request submitted", "request_id": 10},
                )
            return httpx.Response(401, json={"detail": "Unauthorized"})

        if path == "/api/v1/auth/refresh":
            if body.get("refresh_token") == "valid_refresh_token_123":
                return httpx.Response(
                    200,
                    json={"access_token": new_access_token, "token_type": "bearer"},
                )
            return httpx.Response(401, json={"detail": "Invalid refresh token"})

        if path == "/api/v1/auth/logout":
            return httpx.Response(200, json={"message": "Logged out successfully."})

        return httpx.Response(404, json={"detail": "Not found"})

    async def _test():
        transport = httpx.MockTransport(mock_backend_handler)
        client = ApiClient(base_url="http://testserver", transport=transport)

        # 1. Health check
        health = await client.check_health()
        assert health.success
        assert health.data == {"status": "ok"}

        # 2. Register
        reg_res = await client.register(
            email="tester@pw.edu.pl",
            password="SecurePassword123!",
            display_name="Tester",
        )
        assert reg_res.success
        assert reg_res.data["user_id"] == 1

        # 3. Bad login
        bad_login = await client.login("tester@pw.edu.pl", "WrongPassword")
        assert not bad_login.success
        assert bad_login.status_code == 401
        assert "Incorrect" in bad_login.error

        # 4. Correct login
        login_res = await client.login("tester@pw.edu.pl", "SecurePassword123!")
        assert login_res.success
        assert client.access_token == valid_access_token
        assert client.get_refresh_token() == "valid_refresh_token_123"
        assert client.get_current_role() == "USER"

        # 5. Get me
        me_res = await client.get_me()
        assert me_res.success
        assert me_res.data["email"] == "tester@pw.edu.pl"

        # 6. Request role
        role_res = await client.request_role("RESEARCHER")
        assert role_res.success
        assert role_res.data["request_id"] == 10

        # 7. Refresh token
        refresh_res = await client.refresh()
        assert refresh_res.success
        assert client.access_token == new_access_token

        # 8. Auto-login
        # Mock me returning data for valid token
        client.access_token = valid_access_token
        auto_res = await client.auto_login()
        assert auto_res.success

        # 9. Logout
        logout_res = await client.logout()
        assert logout_res.success
        assert client.access_token is None
        assert client.get_refresh_token() is None

        # 10. Subsequent authenticated call fails
        fail_me = await client.get_me()
        assert not fail_me.success
        assert fail_me.status_code == 401

    asyncio.run(_test())
