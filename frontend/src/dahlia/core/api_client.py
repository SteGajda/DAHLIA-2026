"""REST API client for communicating with DAHLIA backend.

Handles HTTP requests via HTTPX, manages session tokens (RAM for Access Token,
system keyring for Refresh Token), decodes JWT claims, and provides comprehensive
offline-first resilience.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

LOGGER = logging.getLogger(__name__)

KEYRING_SERVICE_NAME = "DAHLIA_App"
KEYRING_USERNAME = "refresh_token"


@dataclass
class ApiResult:
    """Standardised result wrapper for all API operations."""

    success: bool
    data: Any = None
    error: str | None = None
    is_offline: bool = False
    status_code: int | None = None


class ApiClient:
    """Asynchronous HTTP client for the DAHLIA backend REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialise API client.

        Parameters
        ----------
        base_url:
            Root URL of the backend (e.g. ``http://127.0.0.1:8000``). Defaults to
            the ``DAHLIA_API_URL`` environment variable or ``http://127.0.0.1:8000``.
        timeout:
            Network request timeout in seconds.
        transport:
            Optional custom HTTP transport (e.g. for testing via ASGITransport).
        """
        raw_url = base_url or os.getenv("DAHLIA_API_URL", "http://127.0.0.1:8000")
        self.base_url = raw_url.rstrip("/")
        self.timeout = timeout if timeout is not None else float(os.getenv("DAHLIA_API_TIMEOUT", "5"))
        if self.timeout <= 0 or not self.timeout < float("inf"):
            raise ValueError("DAHLIA_API_TIMEOUT must be positive and finite.")
        self.keyring_service = (
            KEYRING_SERVICE_NAME
            if self.base_url == "http://127.0.0.1:8000"
            else KEYRING_SERVICE_NAME + ":" + hashlib.sha256(self.base_url.encode()).hexdigest()[:32]
        )
        self.transport = transport

        # Ephemeral session token (kept only in RAM)
        self.access_token: str | None = None

    # Keyring helpers for Refresh Token
    def save_refresh_token(self, token: str) -> bool:
        """Persist refresh token into OS credential store (Windows Credential Manager)."""
        try:
            import keyring

            keyring.set_password(self.keyring_service, KEYRING_USERNAME, token)
            return True
        except Exception as err:
            LOGGER.warning("Could not persist refresh token to keyring: %s", err)
            return False

    def get_refresh_token(self) -> str | None:
        """Retrieve stored refresh token from OS credential store."""
        try:
            import keyring

            return keyring.get_password(self.keyring_service, KEYRING_USERNAME)
        except Exception as err:
            LOGGER.warning("Could not read refresh token from keyring: %s", err)
            return None

    def delete_refresh_token(self) -> bool:
        """Remove refresh token from OS credential store."""
        try:
            import keyring

            keyring.delete_password(self.keyring_service, KEYRING_USERNAME)
            return True
        except Exception as err:
            LOGGER.debug("Could not delete refresh token from keyring (may not exist): %s", err)
            return False

    def clear_session(self) -> None:
        """Clear both in-memory access token and persisted refresh token."""
        self.access_token = None
        self.delete_refresh_token()

    # JWT inspection
    @staticmethod
    def decode_token_payload(token: str) -> dict[str, Any] | None:
        """Decode claims from a JWT without validating signature (client-side inspect)."""
        try:
            return jwt.decode(token, options={"verify_signature": False})
        except Exception as err:
            LOGGER.debug("Failed to decode token payload: %s", err)
            return None

    def get_current_role(self) -> str | None:
        """Extract role_code claim from current in-memory access token if present."""
        if not self.access_token:
            return None
        claims = self.decode_token_payload(self.access_token)
        if claims and "role_code" in claims:
            return str(claims["role_code"])
        return None

    # Internal HTTP transport helper
    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        auth: bool = False,
        headers: dict[str, str] | None = None,
    ) -> ApiResult:
        """Perform HTTP request, handling authentication headers and offline errors."""
        url = f"{self.base_url}{path}"
        req_headers = dict(headers or {})

        if auth:
            if not self.access_token:
                return ApiResult(
                    success=False,
                    error="Not authenticated: no access token available.",
                    status_code=401,
                )
            req_headers["Authorization"] = f"Bearer {self.access_token}"

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    json=json,
                    headers=req_headers,
                )

            # Parse response
            status_code = response.status_code
            try:
                data = response.json()
            except Exception:
                data = response.text

            if 200 <= status_code < 300:
                return ApiResult(success=True, data=data, status_code=status_code)

            # Extract error message from API response
            error_message: str = f"Request failed with status {status_code}"
            if isinstance(data, dict):
                if "detail" in data:
                    detail = data["detail"]
                    if isinstance(detail, list):
                        error_message = "; ".join(
                            d.get("msg", str(d)) for d in detail if isinstance(d, dict)
                        )
                    else:
                        error_message = str(detail)
                elif "message" in data:
                    error_message = str(data["message"])

            return ApiResult(
                success=False,
                error=error_message,
                data=data,
                status_code=status_code,
            )

        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError):
            LOGGER.info("Backend service unreachable at %s (offline mode)", url)
            return ApiResult(
                success=False,
                error="Cannot connect to server. Running in offline mode.",
                is_offline=True,
            )
        except httpx.TimeoutException:
            LOGGER.info("Backend request timed out at %s (offline mode)", url)
            return ApiResult(
                success=False,
                error="Server request timed out. Running in offline mode.",
                is_offline=True,
            )
        except httpx.RequestError as err:
            LOGGER.warning("HTTP request error to %s: %s", url, err)
            return ApiResult(
                success=False,
                error=f"Network error: {err}",
                is_offline=True,
            )
        except Exception as err:
            LOGGER.exception("Unexpected error during API request: %s", err)
            return ApiResult(
                success=False,
                error=f"Unexpected error: {err}",
            )

    # Health / Liveness
    async def check_health(self) -> ApiResult:
        """Check if backend service is reachable and returning valid health JSON."""
        res = await self._request("GET", "/health")
        if res.success:
            if not isinstance(res.data, dict) or res.data.get("status") != "ok":
                LOGGER.info("Health check returned non-API payload (not DAHLIA backend)")
                return ApiResult(
                    success=False,
                    error="Cannot connect to DAHLIA backend. Running in offline mode.",
                    is_offline=True,
                )
        return res

    # Authentication endpoints
    async def login(self, email: str, password: str) -> ApiResult:
        """Authenticate user with email and password.

        On success, stores access token in RAM and refresh token in keyring.
        """
        payload = {"email": email.strip(), "password": password}
        result = await self._request("POST", "/api/v1/auth/login", json=payload)

        if result.success and isinstance(result.data, dict):
            access = result.data.get("access_token")
            refresh = result.data.get("refresh_token")
            if access:
                self.access_token = str(access)
            if refresh:
                self.save_refresh_token(str(refresh))

        return result

    async def register(
        self,
        email: str,
        password: str,
        display_name: str,
        is_pw_affiliated: bool = False,
        student_id_number: str | None = None,
        consent_given: bool = True,
    ) -> ApiResult:
        """Register a new user account."""
        payload = {
            "email": email.strip(),
            "password": password,
            "display_name": display_name.strip(),
            "is_pw_affiliated": is_pw_affiliated,
            "student_id_number": student_id_number.strip() if student_id_number else None,
            "consent_given": consent_given,
        }
        return await self._request("POST", "/api/v1/auth/register", json=payload)

    async def refresh(self, refresh_token: str | None = None) -> ApiResult:
        """Exchange stored refresh token for a new access token."""
        token = refresh_token or self.get_refresh_token()
        if not token:
            return ApiResult(
                success=False,
                error="No refresh token available.",
                status_code=401,
            )

        payload = {"refresh_token": token}
        result = await self._request("POST", "/api/v1/auth/refresh", json=payload)

        if result.success and isinstance(result.data, dict):
            access = result.data.get("access_token")
            if access:
                self.access_token = str(access)
        elif result.status_code == 401:
            # Refresh token is revoked or expired -> clear session
            LOGGER.info("Refresh token is invalid or expired. Clearing local session.")
            self.clear_session()

        return result

    async def auto_login(self) -> ApiResult:
        """Attempt silent re-authentication on startup using saved refresh token.

        Returns UserMeResponse data on success.
        """
        token = self.get_refresh_token()
        if not token:
            return ApiResult(success=False, error="No saved session found.")

        refresh_res = await self.refresh(token)
        if not refresh_res.success:
            return refresh_res

        # Fetch authenticated user profile
        return await self.get_me()

    async def logout(self) -> ApiResult:
        """Revoke refresh token on backend and clear local session."""
        token = self.get_refresh_token()
        result = ApiResult(success=True)

        if token:
            result = await self._request(
                "POST",
                "/api/v1/auth/logout",
                json={"refresh_token": token},
            )

        self.clear_session()
        return result

    async def get_me(self) -> ApiResult:
        """Fetch current authenticated user profile."""
        return await self._request("GET", "/api/v1/auth/me", auth=True)

    async def request_role(self, requested_role: str) -> ApiResult:
        """Submit a role-upgrade request (USER_PLUS or RESEARCHER)."""
        payload = {"requested_role": requested_role}
        return await self._request("POST", "/api/v1/auth/request-role", json=payload, auth=True)

    async def verify_email(self, token: str) -> ApiResult:
        """Activate account using email verification token."""
        return await self._request("POST", "/api/v1/auth/verify-email", json={"token": token})

    async def resend_verification(self) -> ApiResult:
        """Send a verification link to the authenticated account's own address."""
        return await self._request("POST", "/api/v1/auth/resend-verification", auth=True)

    async def forgot_password(self, email: str) -> ApiResult:
        """Request a password reset link."""
        return await self._request("POST", "/api/v1/auth/forgot-password", json={"email": email.strip()})

    async def reset_password(self, token: str, new_password: str) -> ApiResult:
        """Reset account password using reset token."""
        return await self._request(
            "POST",
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": new_password},
        )

    # Admin endpoints (requires DEVELOPER role)
    async def list_role_requests(self) -> ApiResult:
        """List pending role upgrade requests."""
        return await self._request("GET", "/api/v1/admin/role-requests", auth=True)

    async def approve_role_request(self, request_id: int) -> ApiResult:
        """Approve a pending role upgrade request."""
        return await self._request(
            "POST",
            f"/api/v1/admin/role-requests/{request_id}/approve",
            auth=True,
        )

    async def reject_role_request(self, request_id: int) -> ApiResult:
        """Reject a pending role upgrade request."""
        return await self._request(
            "POST",
            f"/api/v1/admin/role-requests/{request_id}/reject",
            auth=True,
        )

    # Sync endpoints
    async def get_database_access(self) -> ApiResult:
        return await self._request("GET", "/api/v1/database-access/me", auth=True)

    async def issue_sql_credentials(self, client_ipv4: str) -> ApiResult:
        return await self._request("POST", "/api/v1/database-access/credentials",
                                   json={"client_ipv4": client_ipv4.strip()}, auth=True)

    async def sync_experiment(self, payload: dict[str, Any]) -> ApiResult:
        """Upload a completed experiment record to the central database."""
        return await self._request("POST", "/api/v1/sync/experiment", json=payload, auth=True)

