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
from typing import Literal
from urllib.parse import urlsplit

from pydantic import EmailStr, Field, SecretStr, model_validator
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

    SQL_ACCESS_ENABLED: bool = False
    SQL_ACCESS_HOST: str = "dahlia-2026.database.windows.net"
    SQL_ACCESS_DATABASE: str = "DAHLIA"

    # Disabled until an administrator configures a real sender.
    EMAIL_DELIVERY_MODE: Literal["disabled", "smtp"] = "disabled"
    PUBLIC_API_URL: str = "http://127.0.0.1:8000"
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = Field(default=587, ge=1, le=65535)
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: SecretStr = SecretStr("")
    SMTP_FROM_EMAIL: EmailStr = "dahlia.imputation@gmail.com"
    SMTP_TIMEOUT_SECONDS: int = Field(default=20, ge=1, le=60)
    EMAIL_RESEND_COOLDOWN_SECONDS: int = Field(default=60, ge=60, le=86400)

    @model_validator(mode="after")
    def validate_email_settings(self):
        if self.EMAIL_DELIVERY_MODE == "smtp":
            url = urlsplit(self.PUBLIC_API_URL)
            local = url.hostname in {"127.0.0.1", "localhost", "::1"}
            if (not url.hostname or url.username or url.password or url.query
                    or url.fragment or url.path not in {"", "/"}
                    or (url.scheme != "https" and not (local and url.scheme == "http"))):
                raise ValueError("PUBLIC_API_URL must be an HTTPS origin (HTTP is allowed on localhost).")
            if not self.SMTP_HOST or not self.SMTP_USERNAME or not self.SMTP_PASSWORD.get_secret_value():
                raise ValueError("SMTP host, username and app password are required in smtp mode.")
        return self

    model_config = SettingsConfigDict(
        hide_input_in_errors=True,
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
