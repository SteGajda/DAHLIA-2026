"""API v1 main router — aggregates all v1 sub-routers."""

from __future__ import annotations

from fastapi import APIRouter
from app.api.v1 import admin, auth, sync, database_access, datasets, predefined_sets

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(admin.router, prefix="/admin", tags=["admin"])
router.include_router(sync.router, prefix="/sync", tags=["sync"])
router.include_router(database_access.router, prefix="/database-access", tags=["database-access"])
router.include_router(datasets.router, prefix="/datasets", tags=["datasets"])
router.include_router(predefined_sets.router, prefix="/predefined-sets", tags=["predefined-sets"])

