"""SQLAlchemy ORM models for user accounts, sessions and role requests.

This module defines three tables in the ``dahlia`` schema:

* :class:`AppUser` — ``dahlia.app_user``: user accounts with roles and PW affiliation metadata.
* :class:`RefreshToken` — ``dahlia.refresh_token``: hashed long-lived session tokens.
* :class:`RoleRequest` — ``dahlia.role_request``: queue of role-upgrade requests.

Schema note
-----------
All tables use ``__table_args__ = {"schema": "dahlia"}``.

* **MS SQL Server / Azure SQL**: the schema must exist before running migrations.
* **SQLite** (dev-loop): ``schema_translate_map={"dahlia": None}`` is applied
  at the engine level (see ``session.py``), stripping the prefix from every
  DDL and DML statement.

Role codes
----------
* ``USER``: Default role assigned on registration.
* ``USER_PLUS``: Read access to the central results database.
* ``RESEARCHER``: Full read/write access to results, experiment configuration, and predefined imputation sets.
* ``DEVELOPER``: Highest administrative role (user/dataset management).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

# Allowed role codes (used in CHECK constraints and application logic)
VALID_ROLE_CODES: frozenset[str] = frozenset(
    {"USER", "USER_PLUS", "RESEARCHER", "DEVELOPER"}
)

# Allowed role-request statuses
VALID_REQUEST_STATUSES: frozenset[str] = frozenset(
    {"PENDING", "APPROVED", "REJECTED"}
)


def _utcnow() -> datetime:
    """Return the current UTC-aware datetime.

    Used as a ``default`` callable for :class:`~sqlalchemy.orm.mapped_column`
    so that each row receives the correct timestamp at INSERT time.

    Returns
    -------
    datetime
        Current time in UTC with timezone information attached.
    """
    return datetime.now(timezone.utc)


# AppUser
class AppUser(Base):
    """ORM model for the ``dahlia.app_user`` table.

    Represents a DAHLIA user account.  Every account starts with the
    ``USER`` role and may be upgraded via :class:`RoleRequest`.

    Attributes
    ----------
    user_id : int
        Auto-incrementing primary key.
    email : str
        Unique email address used as login.
    display_name : str
        User-chosen display name.
    password_hash : str
        Hash of the user's password.
    role_code : str
        Access level.
    is_pw_affiliated : bool
        ``True`` if the user declared affiliation with WUT.
    student_id_number : str | None
        Index number. Required if affiliated.
    consent_given : bool
        Whether the user agreed to data processing.
    is_email_verified : bool
        Verification status.
    is_active : bool
        Soft-delete flag.
    created_at : datetime
        UTC timestamp of account creation.
    refresh_tokens : list of RefreshToken
        Associated refresh tokens.
    role_requests : list of RoleRequest
        Associated role upgrade requests.
    """

    __tablename__ = "app_user"
    __table_args__ = {"schema": "dahlia"}

    user_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_code: Mapped[str] = mapped_column(
        String(20), nullable=False, default="USER"
    )
    is_pw_affiliated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    student_id_number: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    consent_given: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # Relationships
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    role_requests: Mapped[list[RoleRequest]] = relationship(
        "RoleRequest",
        foreign_keys="[RoleRequest.user_id]",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AppUser id={self.user_id} email={self.email!r}"
            f" role={self.role_code!r}>"
        )


# RefreshToken
class RefreshToken(Base):
    """ORM model for the ``dahlia.refresh_token`` table.

    Stores hashed long-lived Refresh Tokens used by the desktop client to
    obtain new Access Tokens without asking the user for their password.

    Security design
    ---------------
    Only the **SHA-256 hash** of the token is persisted here.  The raw token
    string is returned to the client exactly once (at login) and never stored
    in plaintext on the server side.

    Attributes
    ----------
    token_id : int
        Auto-incrementing primary key.
    user_id : int
        Foreign key to :class:`AppUser`.
    token_hash : str
        SHA-256 hash (hex digest) of the raw Refresh Token.
    expires_at : datetime
        UTC expiry datetime.
    revoked : bool
        Explicit revocation flag.
    created_at : datetime
        UTC timestamp when the token was issued.
    user : AppUser
        Owning user account.
    """

    __tablename__ = "refresh_token"
    __table_args__ = {"schema": "dahlia"}

    token_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dahlia.app_user.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # Relationships
    user: Mapped[AppUser] = relationship(
        "AppUser", back_populates="refresh_tokens"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RefreshToken id={self.token_id} user_id={self.user_id}"
            f" revoked={self.revoked}>"
        )


# RoleRequest
class RoleRequest(Base):
    """ORM model for the ``dahlia.role_request`` table.

    Tracks role-upgrade requests submitted by users.  A DEVELOPER reviews
    pending requests and either approves or rejects them.

    Workflow
    --------
    1. User sends ``POST /api/v1/auth/request-role`` →
       a new ``PENDING`` record is created.
    2. DEVELOPER fetches ``GET /api/v1/admin/role-requests`` →
       sees all ``PENDING`` entries.
    3. DEVELOPER calls ``POST /api/v1/admin/role-requests/{id}/approve``
       or ``…/reject`` → :attr:`status` is updated and
       :attr:`AppUser.role_code` is changed accordingly.

    Attributes
    ----------
    request_id : int
        Auto-incrementing primary key.
    user_id : int
        Foreign key to the requesting :class:`AppUser`.
    requested_role : str
        Target role code.
    status : str
        Current state of the request.
    created_at : datetime
        UTC timestamp when the request was submitted.
    reviewed_by : int | None
        ``user_id`` of the reviewer.
    reviewed_at : datetime | None
        UTC timestamp of the review decision.
    user : AppUser
        Requesting user account.
    reviewer : AppUser | None
        Reviewing user account.
    """

    __tablename__ = "role_request"
    __table_args__ = {"schema": "dahlia"}

    request_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dahlia.app_user.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("dahlia.app_user.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped[AppUser] = relationship(
        "AppUser",
        foreign_keys=[user_id],
        back_populates="role_requests",
    )
    reviewer: Mapped[AppUser | None] = relationship(
        "AppUser",
        foreign_keys=[reviewed_by],
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RoleRequest id={self.request_id} user_id={self.user_id}"
            f" role={self.requested_role!r} status={self.status!r}>"
        )
