"""Admin endpoints for role-upgrade request management.

Access restricted to DEVELOPER role via ``require_role``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.session import get_db
from app.models.user import AppUser, RoleRequest

router = APIRouter()


class RoleRequestOut(BaseModel):
    request_id: int
    user_id: int
    requested_role: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RoleRequestAction(BaseModel):
    message: str
    request_id: int
    new_status: str


@router.get(
    "/role-requests",
    response_model=list[RoleRequestOut],
    summary="List pending role-upgrade requests",
)
def list_role_requests(
    db: Session = Depends(get_db),
    reviewer: AppUser = Depends(require_role("DEVELOPER")),
) -> list[RoleRequest]:
    return (
        db.query(RoleRequest)
        .filter(RoleRequest.status == "PENDING")
        .order_by(RoleRequest.created_at)
        .all()
    )


@router.post(
    "/role-requests/{request_id}/approve",
    response_model=RoleRequestAction,
    summary="Approve a role-upgrade request",
)
def approve_role_request(
    request_id: int,
    db: Session = Depends(get_db),
    reviewer: AppUser = Depends(require_role("DEVELOPER")),
) -> RoleRequestAction:
    req = db.get(RoleRequest, request_id)
    if req is None or req.status != "PENDING":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending request not found.")

    user = db.get(AppUser, req.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    user.role_code = req.requested_role
    req.status = "APPROVED"
    req.reviewed_by = reviewer.user_id
    req.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    return RoleRequestAction(
        message=f"Request approved. User {user.email} is now '{req.requested_role}'.",
        request_id=request_id,
        new_status="APPROVED",
    )


@router.post(
    "/role-requests/{request_id}/reject",
    response_model=RoleRequestAction,
    summary="Reject a role-upgrade request",
)
def reject_role_request(
    request_id: int,
    db: Session = Depends(get_db),
    reviewer: AppUser = Depends(require_role("DEVELOPER")),
) -> RoleRequestAction:
    req = db.get(RoleRequest, request_id)
    if req is None or req.status != "PENDING":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending request not found.")

    req.status = "REJECTED"
    req.reviewed_by = reviewer.user_id
    req.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    return RoleRequestAction(
        message=f"Request {request_id} rejected.",
        request_id=request_id,
        new_status="REJECTED",
    )
