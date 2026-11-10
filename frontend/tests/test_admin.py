"""Unit tests for Admin Panel screen and DEVELOPER role workflows."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
import httpx
import pytest

from dahlia.app.controller import AppController
from dahlia.core.api_client import ApiClient, ApiResult


def test_show_admin_guard_non_developer():
    """Verify that users without DEVELOPER role are guarded from accessing Admin screen."""
    mock_root = MagicMock()
    controller = AppController(root=mock_root)
    controller.show_profile = MagicMock()
    controller._clear = MagicMock()
    controller._set_exit_guard = MagicMock()

    # 1. Not logged in
    controller.current_user = None
    controller.show_admin()
    controller.show_profile.assert_called_once()
    assert controller.active_screen != "admin"

    # 2. Logged in as USER
    controller.show_profile.reset_mock()
    controller.current_user = {"email": "user@pw.edu.pl", "role": "USER"}
    controller.show_admin()
    controller.show_profile.assert_called_once()
    assert controller.active_screen != "admin"

    # 3. Logged in as RESEARCHER
    controller.show_profile.reset_mock()
    controller.current_user = {"email": "res@pw.edu.pl", "role": "RESEARCHER"}
    controller.show_admin()
    controller.show_profile.assert_called_once()
    assert controller.active_screen != "admin"


def test_show_admin_allowed_for_developer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that DEVELOPER role can access Admin screen."""
    mock_root = MagicMock()
    controller = AppController(root=mock_root)
    controller._clear = MagicMock()
    controller._set_exit_guard = MagicMock()
    mock_render = MagicMock()
    monkeypatch.setattr("dahlia.app.controller.render_admin", mock_render)

    controller.current_user = {"email": "dev@pw.edu.pl", "role": "DEVELOPER"}
    # Call show_admin
    controller.show_admin()
    assert controller.active_screen == "admin"
    controller._clear.assert_called_once()
    controller._set_exit_guard.assert_called_once_with(False)
    mock_render.assert_called_once_with(controller)


def test_admin_api_endpoints_mock_transport():
    """Verify that ApiClient admin methods format requests and handle responses."""
    def mock_admin_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return httpx.Response(401, json={"detail": "Unauthorized"})

        if path == "/api/v1/admin/role-requests":
            return httpx.Response(
                200,
                json=[
                    {
                        "request_id": 1,
                        "user_id": 10,
                        "requested_role": "USER_PLUS",
                        "status": "PENDING",
                        "created_at": "2026-02-01T12:00:00",
                    },
                    {
                        "request_id": 2,
                        "user_id": 11,
                        "requested_role": "RESEARCHER",
                        "status": "PENDING",
                        "created_at": "2026-02-01T12:05:00",
                    },
                ],
            )

        if path == "/api/v1/admin/role-requests/1/approve":
            return httpx.Response(
                200,
                json={
                    "message": "Request approved.",
                    "request_id": 1,
                    "new_status": "APPROVED",
                },
            )

        if path == "/api/v1/admin/role-requests/2/reject":
            return httpx.Response(
                200,
                json={
                    "message": "Request rejected.",
                    "request_id": 2,
                    "new_status": "REJECTED",
                },
            )

        return httpx.Response(404, json={"detail": "Not found"})

    async def _test():
        transport = httpx.MockTransport(mock_admin_handler)
        client = ApiClient(base_url="http://testserver", transport=transport)
        client.access_token = "valid_dev_token"

        # 1. List requests
        list_res = await client.list_role_requests()
        assert list_res.success
        assert len(list_res.data) == 2
        assert list_res.data[0]["request_id"] == 1
        assert list_res.data[0]["requested_role"] == "USER_PLUS"
        assert list_res.data[1]["requested_role"] == "RESEARCHER"

        # 2. Approve request
        approve_res = await client.approve_role_request(1)
        assert approve_res.success
        assert approve_res.data["new_status"] == "APPROVED"

        # 3. Reject request
        reject_res = await client.reject_role_request(2)
        assert reject_res.success
        assert reject_res.data["new_status"] == "REJECTED"

        # 4. Without token -> 401
        client.access_token = None
        fail_res = await client.list_role_requests()
        assert not fail_res.success
        assert fail_res.status_code == 401

    asyncio.run(_test())
