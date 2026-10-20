"""Authenticated activation of an individual read-only SQL account."""

from ipaddress import IPv4Address

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import AppUser
from app.services.database_access import connection_details, issue_credentials

router = APIRouter()


class AccessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_ipv4: str

    @field_validator("client_ipv4")
    @classmethod
    def public_ipv4(cls, value):
        ip = IPv4Address(value.strip())
        if not ip.is_global or ip.is_multicast:
            raise ValueError("Enter your computer's public IPv4 address, not a local or private address.")
        return str(ip)


@router.get("/me")
def access_status(response: Response, user: AppUser = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    return connection_details(user)


@router.post("/credentials")
def create_or_reset_credentials(
    payload: AccessRequest, response: Response,
    user: AppUser = Depends(get_current_user), db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return issue_credentials(db, user, payload.client_ipv4)
