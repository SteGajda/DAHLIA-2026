"""Pytest fixtures shared across all runtime tests.

``starlette.testclient`` accesses ``anyio.abc.BlockingPortal`` at module-level
(line 53), which triggers a ``DeprecationWarning`` from anyio 4.x.  To suppress
it, ``TestClient`` must **not** be imported at module level in this file.
Instead, the import is deferred to inside the ``client`` fixture body, which
runs after all warning filters (``pyproject.toml`` + ``pytest_configure``) are
already active.

Fixtures
--------
``sqlite_engine``
    Fresh SQLite in-memory engine with ``schema_translate_map={"dahlia": None}``
    applied at engine level.  Every connection (DDL, ORM queries, DML) gets
    the map automatically.  Tables are created via ``Base.metadata.create_all()``.

``sqlite_session``
    A SQLAlchemy Session bound to the ``sqlite_engine`` fixture.

``test_app``
    The FastAPI application with ``get_db`` overridden to use the test engine.

``client``
    Starlette's ``TestClient`` wrapping ``test_app``.
"""

from __future__ import annotations

import warnings


def pytest_configure(config):  # noqa: ARG001
    """Register warning filters before any test module is imported.

    ``starlette.testclient`` emits an anyio ``DeprecationWarning`` at line 53
    of the module body (i.e., at import time).  pytest processes
    ``filterwarnings`` from ``pyproject.toml`` after collecting test files,
    which is already too late.  A ``pytest_configure`` hook runs first,
    before any test module import, so the filter is active in time.
    """
    warnings.filterwarnings(
        "ignore",
        message="The anyio.abc.BlockingPortal alias is deprecated",
        category=DeprecationWarning,
    )


import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
# NOTE: starlette.testclient is intentionally NOT imported here at module level.
# See the module docstring for why — deferred import in client() fixture below.

from app.db.base import Base
from app.db.session import get_db


# ---------------------------------------------------------------------------
# SQLite in-memory engine — fully isolated per test
# ---------------------------------------------------------------------------
@pytest.fixture()
def sqlite_engine():
    """Create a fresh SQLite in-memory engine with all ORM tables.

    ``schema_translate_map={"dahlia": None}`` is applied at the engine level
    so that **both** DDL (``create_all``) and all subsequent ORM queries /
    DML statements transparently strip the ``dahlia.`` schema prefix.
    This mirrors the production session.py behaviour for SQLite.
    """
    _engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    _engine = _engine.execution_options(schema_translate_map={"dahlia": None})
    Base.metadata.create_all(bind=_engine)
    yield _engine
    _engine.dispose()


@pytest.fixture()
def sqlite_session(sqlite_engine):
    """Yield a SQLAlchemy Session bound to the test SQLite engine."""
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=sqlite_engine,
    )
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# FastAPI test application
# ---------------------------------------------------------------------------
@pytest.fixture()
def test_app(sqlite_engine):
    """Return the FastAPI app with ``get_db`` overridden to use the test engine.

    The lifespan (which would run ``create_all`` on the *real* DATABASE_URL)
    is bypassed because TestClient by default does not trigger the ASGI
    lifespan unless explicitly told to.  Our tables already exist courtesy of
    the ``sqlite_engine`` fixture.
    """
    from main import app

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=sqlite_engine,
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()


@pytest.fixture()
def client(test_app):
    """Return a synchronous Starlette TestClient for the FastAPI app.

    Drives the ASGI app in-process; no running uvicorn required.
    ``raise_server_exceptions=True`` surfaces route-handler tracebacks
    directly in test output.

    ``TestClient`` is imported here (not at module level) so that
    ``starlette.testclient`` is loaded only after all warning filters are
    active, preventing the anyio DeprecationWarning from leaking through.
    """
    from starlette.testclient import TestClient  # deferred — see module docstring

    with TestClient(test_app, raise_server_exceptions=True) as c:
        yield c
