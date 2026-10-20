"""API v1 main router — aggregates all v1 sub-routers."""

from __future__ import annotations

from fastapi import APIRouter
from app.api.v1 import admin, auth, sync, database_access

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(admin.router, prefix="/admin", tags=["admin"])
router.include_router(sync.router, prefix="/sync", tags=["sync"])
router.include_router(database_access.router, prefix="/database-access", tags=["database-access"])

