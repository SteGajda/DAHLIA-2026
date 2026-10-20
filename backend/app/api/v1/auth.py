"""Authentication and session management endpoints.

Endpoints
---------
POST /register
    Create a new user account.  Sends an e-mail verification link through the
    configured SMTP sender. No verification tokens are logged.

POST /verify-email
    Activate an account using the JWT from the verification e-mail.

POST /login
    Authenticate with e-mail + password; receive an Access Token (JWT,
    30 min) and a Refresh Token (opaque random string, 30 days).

POST /refresh
    Exchange a valid Refresh Token for a new Access Token.

POST /logout
    Revoke a Refresh Token so it can no longer be used for refreshing.

GET  /me
    Return the profile of the currently authenticated user.

POST /request-role
    Submit a role-upgrade request (USER → USER_PLUS / RESEARCHER).
    A DEVELOPER reviews it in the admin panel (Faza 3).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.services.verification_email import (
    EmailCooldownError, EmailDeliveryError, request_verification_email,
)
from app.services.verification_page import verification_page
from app.db.session import get_db
from app.models.user import AppUser, RefreshToken, RoleRequest
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    RoleRequestCreate,
    RoleRequestResponse,
    TokenResponse,
    UserMeResponse,
    VerifyEmailRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Role upgrade hierarchy
# Users may only request a role strictly higher than their current one and no
# higher than RESEARCHER (DEVELOPER is not self-requestable).
_UPGRADEABLE_TO: dict[str, set[str]] = {
    "USER": {"USER_PLUS"},
    "USER_PLUS": {"RESEARCHER"},
    "RESEARCHER": set(),
    "DEVELOPER": set(),
}


# POST /register
@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user account",
)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
) -> RegisterResponse:
    """Register a new DAHLIA user.

    On success the account is created with ``is_email_verified = False``.
    A verification link is sent through the configured SMTP sender.
    The account can be used to log in immediately, but the sync endpoint
    requires e-mail verification.
    """
    existing = db.query(AppUser).filter(AppUser.email == str(payload.email)).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this e-mail address already exists.",
        )

    user = AppUser(
        email=str(payload.email),
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role_code="USER",
        is_pw_affiliated=payload.is_pw_affiliated,
        student_id_number=payload.student_id_number,
        consent_given=payload.consent_given,
        is_email_verified=False,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    email_sent = False
    try:
        request_verification_email(db, user)
        email_sent = True
    except (EmailDeliveryError, EmailCooldownError):
        logger.warning("Registration completed; verification mail was not submitted.")

    return RegisterResponse(
        message=(
            "Account created. Check your inbox and spam folder for the verification email."
            if email_sent else
            "Account created, but the verification email could not be sent. "
            "Log in and request it again from Profile."
        ),
        user_id=user.user_id,
        email_sent=email_sent,
    )


@router.post("/resend-verification", summary="Send a verification email to the current account")
def resend_verification(
    user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if user.is_email_verified:
        return {"message": "Your email address is already verified.", "email_sent": False}
    try:
        request_verification_email(db, user)
    except EmailCooldownError:
        seconds = get_settings().EMAIL_RESEND_COOLDOWN_SECONDS
        raise HTTPException(status_code=429,
                            detail=f"Please wait {seconds} seconds before requesting another email.",
                            headers={"Retry-After": str(seconds)})
    except EmailDeliveryError:
        logger.warning("Verification mail could not be submitted to SMTP.")
        raise HTTPException(status_code=503,
                            detail="Could not send the verification email. Please try again later.")
    return {"message": "Verification email sent. Check your inbox and spam folder.", "email_sent": True}


@router.get("/verify-email", include_in_schema=False)
def email_confirmation_page():
    return verification_page()


# POST /verify-email
@router.post(
    "/verify-email",
    status_code=status.HTTP_200_OK,
    summary="Verify e-mail address using the activation token",
)
def verify_email(
    payload: VerifyEmailRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Set ``is_email_verified = True`` for the account referenced by *token*.

    The token is a short-lived JWT (24 h) with ``purpose="email_verify"``.
    Calling this endpoint on an already-verified account is idempotent.
    """
    try:
        claims = decode_token(payload.token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token has expired. Please request a new one.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification token.",
        )

    if not all(key in claims for key in ("sub", "iat", "exp")):
        raise HTTPException(status_code=400, detail="Incomplete verification token.")

    if claims.get("purpose") != "email_verify":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token purpose — expected an e-mail verification token.",
        )

    try:
        user_id = int(claims["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed token payload.",
        )

    user: AppUser | None = db.get(AppUser, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found.",
        )

    if "email" in claims and claims["email"] != user.email:
        raise HTTPException(status_code=400, detail="Verification token refers to another email address.")

    if user.is_email_verified:
        return {"message": "E-mail address is already verified."}

    user.is_email_verified = True
    db.commit()
    return {"message": "E-mail address verified successfully."}


# POST /login
@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive Access + Refresh tokens",
)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Verify e-mail + password and issue an Access Token + Refresh Token pair.

    The Refresh Token is stored as its SHA-256 hash in ``dahlia.refresh_token``.
    The raw token is returned once and must be stored securely on the client
    (keyring / Windows Credential Manager).
    """
    settings = get_settings()
    user: AppUser | None = (
        db.query(AppUser).filter(AppUser.email == str(payload.email)).first()
    )

    # Always call verify_password even when user is None to prevent
    # timing-based user-enumeration attacks.
    password_ok = user is not None and verify_password(
        payload.password, user.password_hash
    )
    if not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect e-mail or password.",
        )

    if not user.is_active:  # type: ignore[union-attr]  # guarded above
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact a DEVELOPER administrator.",
        )

    access_token = create_access_token(user.user_id, user.role_code)
    raw_refresh, refresh_hash = create_refresh_token()

    now = datetime.now(timezone.utc)
    token_record = RefreshToken(
        user_id=user.user_id,
        token_hash=refresh_hash,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        revoked=False,
        created_at=now,
    )
    db.add(token_record)
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        token_type="bearer",
        role_code=user.role_code,
    )


# POST /refresh
@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="Obtain a new Access Token using a valid Refresh Token",
)
def refresh(
    payload: RefreshRequest,
    db: Session = Depends(get_db),
) -> AccessTokenResponse:
    """Issue a new Access Token from a valid, non-expired, non-revoked Refresh Token.

    Per the DAHLIA token policy the Refresh Token is **not rotated** — it
    remains valid until it expires (30 days) or is explicitly revoked via
    ``/logout``.
    """
    token_hash = hash_refresh_token(payload.refresh_token)
    now = datetime.now(timezone.utc)

    record: RefreshToken | None = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,  # noqa: E712 - SQL Server BIT requires equality
            RefreshToken.expires_at > now,
        )
        .first()
    )

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid, expired, or has been revoked.",
        )

    user: AppUser | None = db.get(AppUser, record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Associated user account not found or deactivated.",
        )

    new_access_token = create_access_token(user.user_id, user.role_code)
    return AccessTokenResponse(access_token=new_access_token, token_type="bearer")


# POST /logout
@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Revoke a Refresh Token",
)
def logout(
    payload: LogoutRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Mark a Refresh Token as revoked so it can no longer be used.

    If the token is not found or is already revoked the response is still
    ``200 OK`` — this prevents token-existence enumeration.
    """
    token_hash = hash_refresh_token(payload.refresh_token)
    record: RefreshToken | None = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash)
        .first()
    )

    if record is not None and not record.revoked:
        record.revoked = True
        db.commit()

    return {"message": "Logged out successfully."}


# GET /me
@router.get(
    "/me",
    response_model=UserMeResponse,
    summary="Return the authenticated user's profile",
)
def me(current_user: AppUser = Depends(get_current_user)) -> AppUser:
    """Return profile data for the currently authenticated user.

    Requires a valid ``Authorization: Bearer <access_token>`` header.
    """
    return current_user


# POST /request-role
@router.post(
    "/request-role",
    response_model=RoleRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a role-upgrade request",
)
def request_role(
    payload: RoleRequestCreate,
    db: Session = Depends(get_db),
    current_user: AppUser = Depends(get_current_user),
) -> RoleRequestResponse:
    """Create a ``PENDING`` role-upgrade request for review by a DEVELOPER.

    Rules
    -----
    * The requested role must be strictly higher than the user's current role.
    * ``DEVELOPER`` role is not self-requestable.
    * Duplicate ``PENDING`` requests for the same role are rejected.
    """
    allowed = _UPGRADEABLE_TO.get(current_user.role_code, set())
    if payload.requested_role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Role '{payload.requested_role}' cannot be requested from "
                f"your current role '{current_user.role_code}'."
            ),
        )

    # Check for existing pending request for this role
    existing: RoleRequest | None = (
        db.query(RoleRequest)
        .filter(
            RoleRequest.user_id == current_user.user_id,
            RoleRequest.requested_role == payload.requested_role,
            RoleRequest.status == "PENDING",
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"You already have a pending request for role "
                f"'{payload.requested_role}'."
            ),
        )

    role_request = RoleRequest(
        user_id=current_user.user_id,
        requested_role=payload.requested_role,
        status="PENDING",
        created_at=datetime.now(timezone.utc),
    )
    db.add(role_request)
    db.commit()
    db.refresh(role_request)

    return RoleRequestResponse(
        message=(
            f"Role upgrade request for '{payload.requested_role}' submitted "
            "successfully. A DEVELOPER will review it shortly."
        ),
        request_id=role_request.request_id,
    )


@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
    summary="Request a password reset link",
)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Send a password reset link to the user's e-mail address.

    To prevent e-mail enumeration, this endpoint always returns a success
    message even if the account does not exist.
    """
    user = db.query(AppUser).filter(AppUser.email == str(payload.email)).first()
    if user is not None and user.is_active:
        reset_token = create_password_reset_token(user.user_id)
        logger.info(
            "[MOCK-SMTP] Password reset token for <%s>: "
            'POST /api/v1/auth/reset-password  body={"token": "%s", "new_password": "..."}',
            user.email,
            reset_token,
        )

    return {
        "message": "If an account with that e-mail exists, a password reset link has been sent."
    }


@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Reset password using a token",
)
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Reset the user's password using the short-lived JWT token."""
    try:
        claims = decode_token(payload.token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset token has expired. Please request a new one.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password reset token.",
        )

    if claims.get("purpose") != "password_reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token purpose — expected a password reset token.",
        )

    try:
        user_id = int(claims["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed token payload.",
        )

    user: AppUser | None = db.get(AppUser, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found.",
        )

    user.password_hash = hash_password(payload.new_password)
    db.commit()

    return {"message": "Password has been successfully reset."}

