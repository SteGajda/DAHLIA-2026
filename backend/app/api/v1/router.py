"""API v1 main router — aggregates all v1 sub-routers."""

from __future__ import annotations

from fastapi import APIRouter
from app.api.v1 import admin, auth

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(admin.router, prefix="/admin", tags=["admin"])
