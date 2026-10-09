"""Security utilities for the DAHLIA backend.

Covers three responsibilities:

1. **Password hashing** — bcrypt via *pwdlib*.
2. **JWT encoding / decoding** — HS256 signed tokens for access tokens and
   the short-lived e-mail verification token.
3. **Refresh token generation** — cryptographically secure random string whose
   SHA-256 hash is stored in the database (raw value never persisted).

All secrets are read from :func:`app.core.config.get_settings` so that this
module works in tests without changes (the same ``SECRET_KEY`` from ``.env``
is used throughout).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import get_settings

# Password hashing — bcrypt via pwdlib
_hasher: PasswordHash = PasswordHash([BcryptHasher()])


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain* suitable for storage."""
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return ``True`` if *plain* matches *hashed*, ``False`` otherwise.

    Never raises — any internal exception is caught and treated as a
    verification failure to avoid leaking implementation details.
    """
    try:
        return _hasher.verify(plain, hashed)
    except Exception:  # noqa: BLE001
        return False


# JWT encoding / decoding — HS256
_ALGORITHM = "HS256"


def create_access_token(user_id: int, role_code: str) -> str:
    """Create a signed JWT access token.

    Claims
    ------
    sub
        String representation of *user_id*.
    role_code
        Current role of the user (e.g. ``"USER"``, ``"RESEARCHER"``).
    type
        Always ``"access"`` — distinguishes this token from other JWT types
        (e.g. email verification) so that tokens cannot be cross-used.
    iat / exp
        Issued-at and expiry timestamps (UTC).  TTL is read from settings.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict = {
        "sub": str(user_id),
        "role_code": role_code,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)


def create_email_verification_token(user_id: int) -> str:
    """Create a short-lived JWT for e-mail address verification (TTL: 24 h).

    The ``purpose`` claim prevents this token from being accepted on any other
    endpoint (e.g. using it as an access token is rejected by the auth deps).
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict = {
        "sub": str(user_id),
        "purpose": "email_verify",
        "iat": now,
        "exp": now + timedelta(hours=24),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)


def create_password_reset_token(user_id: int) -> str:
    """Create a short-lived JWT for password reset (TTL: 15 min).

    The ``purpose`` claim prevents cross-use with other token types.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict = {
        "sub": str(user_id),
        "purpose": "password_reset",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a DAHLIA JWT.

    Raises
    ------
    jwt.ExpiredSignatureError
        When the token's ``exp`` claim is in the past.
    jwt.InvalidTokenError
        For any other invalid / malformed token.
    """
    settings = get_settings()
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALGORITHM])


# Refresh token — random value, stored as SHA-256 hash

def create_refresh_token() -> tuple[str, str]:
    """Generate a cryptographically secure refresh token.

    Returns
    -------
    tuple[str, str]
        ``(raw_token, sha256_hex_hash)`` — the raw token is returned to the
        client once and **never** stored on the server side.  Only the hash
        is persisted in ``dahlia.refresh_token``.
    """
    # 48 bytes → 64-character URL-safe base64 string
    raw = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, token_hash


def hash_refresh_token(raw: str) -> str:
    """Return the SHA-256 hex digest of a raw refresh token.

    Used when verifying tokens supplied by the client against stored hashes.
    """
    return hashlib.sha256(raw.encode()).hexdigest()
