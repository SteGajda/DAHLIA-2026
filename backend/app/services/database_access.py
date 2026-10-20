"""Role-bound SSMS credentials; privileged work is confined to one SQL procedure."""

import secrets

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import AppUser

READ_ROLES = frozenset({"USER_PLUS", "RESEARCHER", "DEVELOPER"})


def eligible(user: AppUser) -> bool:
    return bool(user.is_active and user.is_email_verified and user.role_code in READ_ROLES)


def connection_details(user: AppUser) -> dict:
    settings = get_settings()
    return {
        "eligible": eligible(user),
        "configured": settings.SQL_ACCESS_ENABLED,
        "server": settings.SQL_ACCESS_HOST,
        "database": settings.SQL_ACCESS_DATABASE,
        "username": user.sql_username,
        "client_ipv4": user.sql_client_ipv4,
        "access": "read_only_research_tables",
    }


def issue_credentials(db: Session, user: AppUser, client_ipv4: str) -> dict:
    if not eligible(user):
        raise HTTPException(403, "Verified USER+, RESEARCHER or DEVELOPER account required.")
    if not get_settings().SQL_ACCESS_ENABLED or db.get_bind().dialect.name != "mssql":
        raise HTTPException(503, "Direct SQL access has not been enabled by the administrator.")

    # Constant character classes satisfy SQL password policy; randomness is 256 bits.
    password = "aA1!" + secrets.token_urlsafe(32)
    try:
        db.execute(text(
            "EXEC dahlia.manage_readonly_access "
            "@user_id=:user_id, @password=:password, @client_ipv4=:ip"
        ), {"user_id": user.user_id, "password": password, "ip": client_ipv4})
        db.commit()
        db.refresh(user)
    except SQLAlchemyError as error:
        db.rollback()
        # Never log this exception: its SQL parameters contain the new password.
        if "51002" in str(getattr(error, "orig", "")):
            raise HTTPException(429, "Wait 60 seconds before generating another SQL password.",
                                headers={"Retry-After": "60"}) from None
        raise HTTPException(503, "Could not activate SQL access. Contact the administrator.") from None
    return {**connection_details(user), "password": password,
            "message": "Save this password now. Generating another one replaces it."}
