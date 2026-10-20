"""Role gates, authenticated identity and secret handling for SQL provisioning.

The owner-executed Azure procedures require the separate live acceptance test.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import get_current_user
from app.models.user import AppUser
from app.services import database_access as service


def user(role="RESEARCHER", active=True, verified=True):
    return AppUser(user_id=12, email="research@example.com", password_hash="unused",
                   role_code=role, is_active=active, is_email_verified=verified)


@pytest.mark.parametrize("role,allowed", [("USER", False), ("USER_PLUS", True),
                                         ("RESEARCHER", True), ("DEVELOPER", True)])
def test_role_eligibility(role, allowed):
    assert service.eligible(user(role)) is allowed
    assert not service.eligible(user(role, active=False))
    assert not service.eligible(user(role, verified=False))


def test_status_requires_authentication(client):
    assert client.get("/api/v1/database-access/me").status_code in (401, 403)
    assert client.post("/api/v1/database-access/credentials", json={"client_ipv4": "8.8.8.8"}).status_code in (401, 403)


def test_connection_details_contain_no_password(client, test_app):
    account = user()
    account.sql_username = "dahlia_ro_12"
    test_app.dependency_overrides[get_current_user] = lambda: account
    response = client.get("/api/v1/database-access/me")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["username"] == "dahlia_ro_12"
    assert "password" not in response.json()


@pytest.mark.parametrize("account", [user("USER"), user(verified=False), user(active=False)])
def test_ineligible_account_cannot_provision(account):
    db = MagicMock()
    with pytest.raises(HTTPException) as error:
        service.issue_credentials(db, account, "8.8.8.8")
    assert error.value.status_code == 403
    db.execute.assert_not_called()


@pytest.mark.parametrize("ip", ["0.0.0.0", "127.0.0.1", "192.168.1.1", "10.0.0.1",
                               "224.1.1.1", "::1", "8.8.8.8; DROP USER dbo", ""])
def test_nonpublic_or_invalid_ip_rejected(client, test_app, ip):
    test_app.dependency_overrides[get_current_user] = lambda: user()
    response = client.post("/api/v1/database-access/credentials", json={"client_ipv4": ip})
    assert response.status_code == 422


def test_caller_cannot_choose_other_user(client, test_app):
    test_app.dependency_overrides[get_current_user] = lambda: user()
    response = client.post("/api/v1/database-access/credentials",
                           json={"client_ipv4": "8.8.8.8", "user_id": 99})
    assert response.status_code == 422


def test_feature_is_disabled_without_configuration():
    with pytest.raises(HTTPException) as error:
        service.issue_credentials(MagicMock(), user(), "8.8.8.8")
    assert error.value.status_code == 503


def configured(monkeypatch):
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(
        SQL_ACCESS_ENABLED=True, SQL_ACCESS_HOST="test.database.windows.net", SQL_ACCESS_DATABASE="DAHLIA"))
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "mssql"
    return db


def test_personal_password_bound_as_parameter_and_not_logged(monkeypatch, caplog):
    db = configured(monkeypatch)
    account = user()
    result = service.issue_credentials(db, account, "8.8.8.8")
    statement, params = db.execute.call_args.args
    assert params["user_id"] == account.user_id
    assert params["ip"] == "8.8.8.8"
    assert params["password"] == result["password"]
    assert len(result["password"]) >= 36
    assert result["password"] not in str(statement) + caplog.text
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(account)


@pytest.mark.parametrize("detail,status", [("51002 private-password", 429), ("private-password", 503)])
def test_provisioning_failure_rolls_back_without_leaking_password(monkeypatch, caplog, detail, status):
    db = configured(monkeypatch)
    error = SQLAlchemyError("sql containing private-password")
    error.orig = detail
    db.execute.side_effect = error
    with pytest.raises(HTTPException) as failure:
        service.issue_credentials(db, user(), "8.8.8.8")
    assert failure.value.status_code == status
    assert "private-password" not in str(failure.value.detail) + caplog.text
    db.rollback.assert_called_once()
    db.commit.assert_not_called()
