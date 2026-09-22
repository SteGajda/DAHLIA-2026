"""Runtime tests for application infrastructure (health check, DB, lifespan).

Verifies that:
- GET /health returns 200 and a valid payload.
- ORM tables are created correctly in SQLite (via create_all and schema_translate_map).
- All three models (AppUser, RefreshToken, RoleRequest) are present in the DB.
"""

from __future__ import annotations

import sqlite3

import pytest


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------
class TestHealthEndpoint:
    """GET /health — liveness check."""

    def test_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_returns_status_ok(self, client):
        response = client.get("/health")
        assert response.json() == {"status": "ok"}

    def test_content_type_is_json(self, client):
        response = client.get("/health")
        assert "application/json" in response.headers["content-type"]


# ---------------------------------------------------------------------------
# SQLite schema bootstrap (create_all + schema_translate_map)
# ---------------------------------------------------------------------------
class TestSQLiteSchemaBootstrap:
    """Verify that all ORM tables land correctly in SQLite via create_all."""

    EXPECTED_TABLES = {"app_user", "refresh_token", "role_request"}

    def test_all_tables_exist(self, sqlite_engine):
        """schema_translate_map strips 'dahlia.' prefix — tables must exist."""
        with sqlite_engine.connect() as conn:
            result = conn.execute(
                # SQLite system table — lists all tables in the database
                __import__("sqlalchemy").text(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            )
            tables = {row[0] for row in result}
        assert self.EXPECTED_TABLES.issubset(tables), (
            f"Missing tables: {self.EXPECTED_TABLES - tables}"
        )

    def test_app_user_columns(self, sqlite_engine):
        """app_user must have the expected columns (spot-check)."""
        with sqlite_engine.connect() as conn:
            result = conn.execute(
                __import__("sqlalchemy").text("PRAGMA table_info(app_user)")
            )
            columns = {row[1] for row in result}
        assert {"user_id", "email", "password_hash", "role_code"}.issubset(columns)

    def test_refresh_token_fk_column(self, sqlite_engine):
        """refresh_token must have user_id FK column."""
        with sqlite_engine.connect() as conn:
            result = conn.execute(
                __import__("sqlalchemy").text("PRAGMA table_info(refresh_token)")
            )
            columns = {row[1] for row in result}
        assert "user_id" in columns

    def test_role_request_columns(self, sqlite_engine):
        """role_request must have the expected columns."""
        with sqlite_engine.connect() as conn:
            result = conn.execute(
                __import__("sqlalchemy").text("PRAGMA table_info(role_request)")
            )
            columns = {row[1] for row in result}
        assert {"request_id", "user_id", "requested_role", "status"}.issubset(columns)


# ---------------------------------------------------------------------------
# ORM model basic smoke test
# ---------------------------------------------------------------------------
class TestORMModels:
    """Verify ORM models can be imported and used without errors."""

    def test_import_models(self):
        from app.models.user import AppUser, RefreshToken, RoleRequest
        assert AppUser.__tablename__ == "app_user"
        assert RefreshToken.__tablename__ == "refresh_token"
        assert RoleRequest.__tablename__ == "role_request"

    def test_models_schema_declaration(self):
        """Models declare schema='dahlia' — used by Alembic on MS SQL."""
        from app.models.user import AppUser
        assert AppUser.__table__.schema == "dahlia"


# ---------------------------------------------------------------------------
# ORM query execution — schema_translate_map works for DML, not just DDL
# ---------------------------------------------------------------------------
class TestORMQueryExecution:
    """Verify that ORM queries execute correctly on SQLite via schema_translate_map.

    Ensures that schema_translate_map is applied to the session/engine, not only
    to create_all, so that runtime queries like session.query(AppUser) work
    without 'unknown database dahlia' errors.
    """

    def test_insert_and_query_app_user(self, sqlite_session):
        """INSERT and SELECT through ORM must work — no 'dahlia.' prefix in SQL."""
        from datetime import datetime, timezone
        from app.models.user import AppUser

        user = AppUser(
            email="test@example.com",
            display_name="Test User",
            password_hash="$2b$12$fakehash",
            role_code="USER",
            is_pw_affiliated=False,
            consent_given=False,
            is_email_verified=False,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        sqlite_session.add(user)
        sqlite_session.commit()

        result = sqlite_session.query(AppUser).filter_by(email="test@example.com").first()
        assert result is not None
        assert result.display_name == "Test User"
        assert result.role_code == "USER"

    def test_empty_table_query(self, sqlite_session):
        """Querying an empty table must return [] not raise an error."""
        from app.models.user import RoleRequest
        result = sqlite_session.query(RoleRequest).all()
        assert result == []

