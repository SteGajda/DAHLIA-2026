"""FastAPI dependency-injection utilities for authentication and RBAC.

Two reusable dependencies are exposed:

``get_current_user``
    Decodes the ``Authorization: Bearer <token>`` header, verifies the
    JWT signature and returns the corresponding :class:`~app.models.user.AppUser`
    ORM object.  Raises ``HTTP 401`` for any authentication failure.

``require_role(*roles)``
    Factory that returns a FastAPI dependency enforcing that the current
    user's ``role_code`` is one of the provided values.  Raises ``HTTP 403``
    on role mismatch.

Usage example::

    @router.get("/admin")
    def admin_only(user: AppUser = Depends(require_role("DEVELOPER"))):
        ...
"""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import AppUser

# Reusable bearer-token extractor — auto-generates "Authorize" button in /docs
_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AppUser:
    """Validate Bearer JWT and return the authenticated :class:`AppUser`.

    Raises
    ------
    HTTP 401
        * Token is expired.
        * Token signature is invalid.
        * Token ``type`` claim is not ``"access"``.
        * User referenced by ``sub`` is not found or deactivated.
    """
    token = credentials.credentials

    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token.",
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — expected an access token.",
        )

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload.",
        )

    user: AppUser | None = db.get(AppUser, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or deactivated.",
        )
    return user


def require_role(*roles: str):
    """Return a dependency that enforces one of the given ``role_code`` values.

    Parameters
    ----------
    *roles:
        One or more role codes from ``{"USER", "USER_PLUS", "RESEARCHER",
        "DEVELOPER"}``.  Access is granted when the authenticated user's
        ``role_code`` is in this set.

    Returns
    -------
    Callable
        A FastAPI dependency that resolves to the authenticated
        :class:`AppUser` or raises ``HTTP 403``.
    """

    def _check_role(
        current_user: AppUser = Depends(get_current_user),
    ) -> AppUser:
        if current_user.role_code not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {', '.join(roles)}.",
            )
        return current_user

    return _check_role
