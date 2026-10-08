"""Alembic migration environment configuration for DAHLIA backend.

This file is executed by Alembic for every migration command
(``alembic upgrade``, ``alembic downgrade``, ``alembic revision --autogenerate``,
``alembic check``, etc.).

Architecture
------------
**Alembic targets MS SQL Server / Azure SQL exclusively.**  SQLite is not a
supported target for Alembic operations in this project.  See
``backend/README.md`` for the full architectural decision and the Docker
snippet for spinning up a local MS SQL Server container.

What this file wires together
------------------------------
1. **Database URL** — read from :func:`app.core.config.get_settings` so that
   the same ``.env`` file drives both the FastAPI application and the
   migration tool.  There is no URL in ``alembic.ini``.
2. **Target metadata** — ``Base.metadata`` from :mod:`app.db.base`.  All
   model classes imported there are visible to autogenerate.
3. **Schema tracking** — ``include_schemas=True`` ensures Alembic tracks
   the ``dahlia`` schema on MS SQL Server / Azure SQL.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make sure `app.*` imports work when alembic is invoked from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Alembic Config object — gives access to values in alembic.ini
config = context.config

# Interpret the config file for Python logging (if present).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject the database URL from application settings
# Single source of truth: the same .env used by the FastAPI app.
# No URL lives in alembic.ini — that file intentionally leaves it empty.
from app.core.config import get_settings  # noqa: E402

_settings = get_settings()
config.set_main_option("sqlalchemy.url", _settings.DATABASE_URL)

# Import Base (and all models registered in app/db/base.py as a side-effect)
from app.db.base import Base  # noqa: E402

target_metadata = Base.metadata


# Offline migrations (generates SQL script — no live DB connection)
def run_migrations_offline() -> None:
    """Run migrations in *offline* mode.

    Alembic generates a SQL script rather than executing DDL against a live
    database.  Useful for code review, deployment approvals, or restricted
    environments where the migration tool cannot connect to production.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# Online migrations (executes DDL directly against the live database)
def run_migrations_online() -> None:
    """Run migrations in *online* mode.

    Alembic connects to the database and executes DDL statements inside a
    transaction.  This is the normal operating mode for ``alembic upgrade``
    and ``alembic downgrade``.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # single-use connection — no pooling for migrations
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            # Compare server-side defaults so autogenerate detects value changes.
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
