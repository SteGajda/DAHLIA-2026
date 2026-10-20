"""Profile refresh and resend without local ownership or account changes."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx

from dahlia.app.controller import AppController
from dahlia.core.api_client import ApiClient, ApiResult
from dahlia.services.local_storage import LocalStorage


def controller():
    result = AppController(MagicMock(), storage=LocalStorage(":memory:"))
    result.current_user = {"user_id": 1, "email": "one@example.com", "is_email_verified": False}
    return result


def test_refresh_enables_verified_profile_without_uploading():
    ctrl = controller()
    ctrl.api_client.get_me = AsyncMock(return_value=ApiResult(success=True, data={
        "user_id": 1, "email": "one@example.com", "is_email_verified": True,
    }))
    ctrl.api_client.sync_experiment = AsyncMock()
    ok, message = asyncio.run(ctrl.refresh_verification_status())
    assert ok and ctrl.current_user["is_email_verified"]
    ctrl.api_client.sync_experiment.assert_not_called()


def test_refresh_does_not_verify_locally_on_failure_or_different_profile():
    ctrl = controller()
    ctrl.api_client.get_me = AsyncMock(return_value=ApiResult(success=False, is_offline=True))
    assert not asyncio.run(ctrl.refresh_verification_status())[0]
    assert not ctrl.current_user["is_email_verified"]
    ctrl.api_client.get_me = AsyncMock(return_value=ApiResult(success=True, data={
        "user_id": 2, "is_email_verified": True,
    }))
    assert not asyncio.run(ctrl.refresh_verification_status())[0]
    assert ctrl.current_user["user_id"] == 1


def test_resend_surfaces_rate_limit_and_does_not_set_verified():
    ctrl = controller()
    ctrl.api_client.resend_verification = AsyncMock(return_value=ApiResult(
        success=False, status_code=429, error="Please wait 60 seconds.",
    ))
    ok, message = asyncio.run(ctrl.resend_verification())
    assert not ok and "60" in message
    assert not ctrl.current_user["is_email_verified"]


def test_account_change_while_refreshing_is_not_overwritten():
    ctrl = controller()
    async def changed():
        ctrl.current_user = {"user_id": 2, "is_email_verified": False}
        return ApiResult(success=True, data={"user_id": 1, "is_email_verified": True})
    ctrl.api_client.get_me = changed
    assert not asyncio.run(ctrl.refresh_verification_status())[0]
    assert ctrl.current_user["user_id"] == 2


def test_resend_uses_authenticated_endpoint():
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"message": "Sent", "email_sent": True})
    client = ApiClient(transport=httpx.MockTransport(handle))
    client.access_token = "test-access"
    assert asyncio.run(client.resend_verification()).success
    assert requests[0].url.path == "/api/v1/auth/resend-verification"
    assert requests[0].headers["Authorization"] == "Bearer test-access"
