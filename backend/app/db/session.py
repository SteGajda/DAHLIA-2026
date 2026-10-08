"""SQLAlchemy engine and session factory for the DAHLIA backend.

This module initialises the synchronous database engine based on the
``DATABASE_URL`` setting and exposes:

* :data:`engine` — the SQLAlchemy :class:`~sqlalchemy.engine.Engine` instance.
* :data:`SessionLocal` — a :class:`~sqlalchemy.orm.sessionmaker` factory bound
  to the engine.
* :func:`get_db` — a FastAPI dependency that yields a database session per
  request and ensures it is closed afterwards.

Supported databases
-------------------
* **SQLite** (dev-loop):
  Used only for quick endpoint testing. Tables are created via
  ``Base.metadata.create_all()`` on startup, not by Alembic.
* **MS SQL Server** (Docker / Azure SQL):
  The authoritative production backend. All schema migrations are
  managed by Alembic targeting this engine.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

# Engine
# Disable thread-check for SQLite to allow FastAPI to share connections across threads.
_connect_args: dict[str, object] = (
    {"check_same_thread": False}
    if _settings.DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    _settings.DATABASE_URL,
    connect_args=_connect_args,
    # pool_pre_ping=True discards stale connections (useful for Azure SQL).
    pool_pre_ping=True,
)

# SQLite schema adapter
# Strip the 'dahlia' schema prefix for SQLite compatibility.
if _settings.DATABASE_URL.startswith("sqlite"):
    engine = engine.execution_options(schema_translate_map={"dahlia": None})

# Session factory
SessionLocal: sessionmaker[Session] = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# FastAPI dependency
def get_db() -> Generator[Session, None, None]:
    """Yield a database session scoped to a single HTTP request.

    This generator is used as a FastAPI dependency via ``Depends(get_db)``.
    The session is always closed in the ``finally`` block, regardless of
    whether the route handler raised an exception.

    Yields
    ------
    Session
        An open SQLAlchemy :class:`~sqlalchemy.orm.Session` bound to the
        configured engine.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
