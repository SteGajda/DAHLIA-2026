"""Application settings loaded from environment variables / .env file.

Settings are read once at startup via :func:`get_settings` and cached with
:func:`functools.lru_cache` so that every module imports the same singleton.

Example usage::

    from app.core.config import get_settings

    settings = get_settings()
    print(settings.DATABASE_URL)

Environment file
----------------
Copy ``backend/.env.example`` to ``backend/.env`` and fill in the values.
The ``.env`` file is excluded from version control via ``.gitignore``.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralised configuration for the DAHLIA backend.

    All fields are read from environment variables (case-insensitive) or from
    a ``.env`` file located in the working directory when the process starts.

    Attributes
    ----------
    DATABASE_URL:
        SQLAlchemy connection string.  Defaults to a local SQLite file so
        that the dev-loop works without any external services::

            sqlite+pysqlite:///./dahlia_dev.db

        For MS SQL Server (local Docker or Azure SQL), set::

            mssql+pyodbc://user:password@host:1433/dahlia_db
            ?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes

    SECRET_KEY:
        Long, cryptographically random string used to sign JWTs.
        Generate with ``openssl rand -hex 32``.
        **Must be set explicitly** — there is no safe default.

    ACCESS_TOKEN_EXPIRE_MINUTES:
        Lifetime of the short-lived JWT Access Token in minutes.
        Default: ``30``.

    REFRESH_TOKEN_EXPIRE_DAYS:
        Lifetime of the long-lived Refresh Token in days.
        Default: ``30``.

    APP_ENV:
        Deployment environment identifier.  One of ``development`` or
        ``production``.  Default: ``development``.
    """

    # Database 
    DATABASE_URL: str = "sqlite+pysqlite:///./dahlia_dev.db"

    # Security / JWT 
    SECRET_KEY: str 

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # General 
    APP_ENV: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Unknown variables in .env are silently ignored so that a shared
        # .env used by both the desktop app and the backend does not cause
        # validation errors.
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the application :class:`Settings` singleton.

    The instance is created once and cached by :func:`functools.lru_cache`.
    Call ``get_settings.cache_clear()`` in tests that need to override
    environment variables.

    Returns
    -------
    Settings
        The validated application configuration object.
    """
    return Settings()  # type: ignore[call-arg]
