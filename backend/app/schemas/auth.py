"""Pydantic schemas for authentication and session management endpoints.

All request / response models used by ``app.api.v1.auth`` live here.
Keeping schemas in a separate module from ORM models enforces a clean
boundary between the API contract and the database layer.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator


# Registration
class RegisterRequest(BaseModel):
    """Request body for ``POST /api/v1/auth/register``."""

    email: EmailStr
    password: str
    display_name: str
    is_pw_affiliated: bool = False
    student_id_number: str | None = None
    consent_given: bool

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return v

    @field_validator("display_name")
    @classmethod
    def display_name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Display name must not be blank.")
        return stripped

    @model_validator(mode="after")
    def student_id_required_when_affiliated(self) -> "RegisterRequest":
        """Enforce that ``student_id_number`` is present and valid (6 digits)
        when the user claims affiliation with Warsaw University of Technology.
        """
        if self.is_pw_affiliated:
            if not self.student_id_number:
                raise ValueError(
                    "student_id_number is required when is_pw_affiliated is True."
                )
            if not re.match(r"^\d{6}$", self.student_id_number):
                raise ValueError(
                    "student_id_number must be exactly 6 digits (e.g. '123456')."
                )
        return self


class RegisterResponse(BaseModel):
    """Response for a successful registration."""

    message: str
    user_id: int


# E-mail verification
class VerifyEmailRequest(BaseModel):
    """Request body for ``POST /api/v1/auth/verify-email``."""

    token: str


# Login / logout
class LoginRequest(BaseModel):
    """Request body for ``POST /api/v1/auth/login``."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Returned on successful login — contains both token types."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role_code: str


class AccessTokenResponse(BaseModel):
    """Returned on successful token refresh — only the new access token."""

    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Request body for ``POST /api/v1/auth/refresh``."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Request body for ``POST /api/v1/auth/logout``."""

    refresh_token: str


# User profile
class UserMeResponse(BaseModel):
    """Response for ``GET /api/v1/auth/me`` — serialised from the ORM model."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    email: str
    display_name: str
    role_code: str
    is_email_verified: bool
    is_pw_affiliated: bool
    consent_given: bool
    created_at: datetime


# Role request
class RoleRequestCreate(BaseModel):
    """Request body for ``POST /api/v1/auth/request-role``."""

    requested_role: str

    @field_validator("requested_role")
    @classmethod
    def valid_requestable_role(cls, v: str) -> str:
        if v not in {"USER_PLUS", "RESEARCHER"}:
            raise ValueError(
                "Only 'USER_PLUS' and 'RESEARCHER' roles can be self-requested."
            )
        return v


class RoleRequestResponse(BaseModel):
    """Response for a successfully submitted role-upgrade request."""

    message: str
    request_id: int


# Password reset
class ForgotPasswordRequest(BaseModel):
    """Request body for ``POST /api/v1/auth/forgot-password``."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Request body for ``POST /api/v1/auth/reset-password``."""

    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return v
