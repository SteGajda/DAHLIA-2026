"""Unit tests for authentication and session flows in AppController."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

from dahlia.app.controller import AppController
from dahlia.core.api_client import ApiClient, ApiResult


@pytest.fixture
def controller():
    """Create an AppController instance with a mocked UI root."""
    mock_root = MagicMock()
    ctrl = AppController(root=mock_root)
    # Mock clear and show_profile to avoid triggering UI rendering in tests
    ctrl._clear = MagicMock()
    ctrl.show_profile = MagicMock()
    return ctrl


def test_do_register_validation(controller):
    """Verify local field validation before attempting API calls."""
    async def _test():
        # 1. Invalid email
        res = await controller.do_register(
            email="invalid",
            username="testuser",
            password="Password123!",
            affiliated=False,
            index_no="",
            agreed=True,
        )
        assert res == "Enter a valid email address."

        # 2. Short password
        res = await controller.do_register(
            email="test@pw.edu.pl",
            username="testuser",
            password="short",
            affiliated=False,
            index_no="",
            agreed=True,
        )
        assert res == "Password must be at least 8 characters long."

        # 3. Affiliated with invalid student index
        res = await controller.do_register(
            email="test@pw.edu.pl",
            username="testuser",
            password="Password123!",
            affiliated=True,
            index_no="123",  # Not 6 digits
            agreed=True,
        )
        assert res == "Student index number must be exactly 6 digits."

        # 4. Terms not agreed
        res = await controller.do_register(
            email="test@pw.edu.pl",
            username="testuser",
            password="Password123!",
            affiliated=False,
            index_no="",
            agreed=False,
        )
        assert res == "You must agree to the data processing terms."

    asyncio.run(_test())


def test_do_register_api_success(controller):
    """Verify successful registration delegates to ApiClient."""
    async def _test():
        controller.api_client.register = AsyncMock(
            return_value=ApiResult(success=True, data={"message": "Created", "user_id": 1})
        )

        res = await controller.do_register(
            email="test@pw.edu.pl",
            username="testuser",
            password="Password123!",
            affiliated=True,
            index_no="123456",
            agreed=True,
        )
        assert res is None
        assert controller.is_online is True

    asyncio.run(_test())


def test_do_login_success_and_profile_population(controller):
    """Verify successful login fetches profile and populates current_user."""
    async def _test():
        controller.api_client.login = AsyncMock(
            return_value=ApiResult(
                success=True,
                data={
                    "access_token": "acc",
                    "refresh_token": "ref",
                    "role_code": "USER",
                },
            )
        )
        controller.api_client.get_me = AsyncMock(
            return_value=ApiResult(
                success=True,
                data={
                    "user_id": 42,
                    "email": "researcher@pw.edu.pl",
                    "display_name": "Dr Researcher",
                    "role_code": "RESEARCHER",
                    "is_pw_affiliated": True,
                    "student_id_number": "654321",
                    "is_email_verified": True,
                },
            )
        )

        res = await controller.do_login("researcher@pw.edu.pl", "SecretPass123!")
        assert res is None
        assert controller.is_online is True
        assert controller.current_user is not None
        assert controller.current_user["email"] == "researcher@pw.edu.pl"
        assert controller.current_user["username"] == "Dr Researcher"
        assert controller.current_user["role"] == "RESEARCHER"
        assert controller.current_user["affiliated"] is True
        assert controller.current_user["index_no"] == "654321"

    asyncio.run(_test())


def test_do_login_offline(controller):
    """Verify offline handling switches is_online to False and returns error message."""
    async def _test():
        controller.api_client.login = AsyncMock(
            return_value=ApiResult(
                success=False,
                error="Cannot connect to server. Running in offline mode.",
                is_offline=True,
            )
        )

        res = await controller.do_login("test@pw.edu.pl", "SecretPass123!")
        assert res == "Cannot connect to server. Running in offline mode."
        assert controller.is_online is False
        assert controller.current_user is None

    asyncio.run(_test())


def test_request_role(controller):
    """Verify role upgrade requests for logged-in users."""
    async def _test():
        # 1. When not logged in
        ok, msg = await controller.request_role("USER_PLUS")
        assert not ok
        assert "logged in" in msg.lower()

        # 2. When logged in as USER, requesting USER_PLUS
        controller.current_user = {"email": "user@pw.edu.pl", "role": "USER"}
        controller.api_client.request_role = AsyncMock(
            return_value=ApiResult(
                success=True,
                data={"message": "Role upgrade request submitted successfully."},
            )
        )

        ok, msg = await controller.request_role("USER_PLUS")
        assert ok
        assert "submitted" in msg.lower()
        controller.api_client.request_role.assert_awaited_with("USER_PLUS")

        # 3. When logged in as USER_PLUS, requesting RESEARCHER
        controller.current_user["role"] = "USER_PLUS"
        ok, msg = await controller.request_role("RESEARCHER")
        assert ok
        controller.api_client.request_role.assert_awaited_with("RESEARCHER")

    asyncio.run(_test())


def test_logout(controller):
    """Verify logout revokes session and resets current_user."""
    async def _test():
        controller.current_user = {"email": "user@pw.edu.pl", "role": "USER"}
        controller.api_client.logout = AsyncMock(return_value=ApiResult(success=True))

        await controller.logout()
        assert controller.current_user is None
        controller.api_client.logout.assert_awaited_once()
        controller.show_profile.assert_called_once()

    asyncio.run(_test())


def test_startup_check_auto_login(controller):
    """Verify silent auto-login on startup when online and saved session exists."""
    async def _test():
        controller.api_client.check_health = AsyncMock(
            return_value=ApiResult(success=True, data={"status": "ok"})
        )
        controller.api_client.auto_login = AsyncMock(
            return_value=ApiResult(
                success=True,
                data={
                    "user_id": 10,
                    "email": "auto@pw.edu.pl",
                    "display_name": "AutoUser",
                    "role_code": "USER_PLUS",
                    "is_pw_affiliated": False,
                    "student_id_number": None,
                    "is_email_verified": True,
                },
            )
        )

        await controller.startup_check()
        assert controller.is_online is True
        assert controller.current_user is not None
        assert controller.current_user["email"] == "auto@pw.edu.pl"
        assert controller.current_user["role"] == "USER_PLUS"

    asyncio.run(_test())
