"""DAHLIA Backend — FastAPI application entry point.

This module creates the :class:`~fastapi.FastAPI` application instance and
registers all API routers.

Database initialisation strategy
--------------------------------
* **MS SQL Server / Azure SQL (production / staging):**
  Schema and tables are managed exclusively by Alembic.
* **SQLite (dev-loop):**
  On startup the application detects a SQLite URL and calls
  ``Base.metadata.create_all()`` through a connection configured with
  ``schema_translate_map={"dahlia": None}``, stripping the schema prefix.
  **Alembic commands must never target SQLite.**
"""

import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import router as api_v1_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine

# Logging — ensure INFO messages (including mock-SMTP tokens) appear in console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)


# Application lifespan
@asynccontextmanager
async def lifespan(application: FastAPI):  # noqa: ARG001
    """Manage startup and shutdown tasks."""
    settings = get_settings()
    if settings.DATABASE_URL.startswith("sqlite"):
        # Initialize SQLite in-memory tables directly via ORM.
        # schema_translate_map in the engine strips the 'dahlia' schema prefix.
        Base.metadata.create_all(bind=engine)

    yield
    # shutdown: nothing to do — SQLAlchemy disposes the pool automatically


# FastAPI application
app = FastAPI(
    title="DAHLIA API",
    description=(
        "REST API for the DAHLIA human-in-the-loop imputation experiment "
        "platform.  Handles authentication, role-based access control (RBAC), "
        "experiment synchronisation and predefined imputation set management."
    ),
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Routers
app.include_router(api_v1_router, prefix="/api/v1")


# Liveness endpoint
@app.get(
    "/health",
    tags=["infra"],
    summary="Liveness check",
    response_description='Always returns {"status": "ok"} when the server is up.',
)
def health_check() -> dict[str, str]:
    """Return a simple liveness signal.

    Returns
    -------
    dict
        ``{"status": "ok"}``
    """
    return {"status": "ok"}
