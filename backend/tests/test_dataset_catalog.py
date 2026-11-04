"""Catalog HTTP contract and authorization against isolated SQLite fixtures."""

import hashlib
from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import mssql
from sqlalchemy.sql import Select

from app.core.security import create_access_token
from app.models.experiment import Dataset
from app.models.user import AppUser

URL = "/api/v1/datasets"


def test_catalog_uses_sql_server_compatible_bit_comparison(
    client, sqlite_engine, sqlite_session, account,
):
    add_dataset(sqlite_session, account, "iris")
    statements = []

    def capture(_conn, clause, _multiparams, _params, _options):
        if isinstance(clause, Select):
            sql = str(clause.compile(dialect=mssql.dialect()))
            if "FROM dahlia.dataset" in sql:
                statements.append(sql)

    event.listen(sqlite_engine, "before_execute", capture)
    try:
        response = client.get(URL, headers=headers(account))
    finally:
        event.remove(sqlite_engine, "before_execute", capture)
    assert response.status_code == 200
    assert response.json()[0]["name"] == "iris"
    assert len(statements) == 1
    assert "dataset.is_active = 1" in statements[0]
    assert "dataset.is_active IS 1" not in statements[0]


@pytest.fixture
def account(sqlite_session):
    user = AppUser(email="catalog@example.com", display_name="Catalog test",
                   password_hash="unused", role_code="RESEARCHER",
                   is_active=True, is_email_verified=True)
    sqlite_session.add(user)
    sqlite_session.commit()
    return user


def headers(account, token_role=None):
    token = create_access_token(account.user_id, token_role or account.role_code)
    return {"Authorization": f"Bearer {token}"}


def add_dataset(db, account, name, *, active=True, row_count=150):
    content = b"Id,value\n1,4.2\n"
    dataset = Dataset(
        name=name, csv_file_name=f"{name}.csv", csv_file=content,
        csv_sha256=hashlib.sha256(content).digest(), row_count=row_count,
        imputed_column="value", target_column=None,
        reference_columns_json="[]", categorical_columns_json="[]",
        precision_value=Decimal("0.1"), created_by=account.user_id,
        is_active=active,
    )
    db.add(dataset)
    db.commit()
    return dataset


@pytest.mark.parametrize("role", ["RESEARCHER", "DEVELOPER"])
def test_both_manager_roles_can_read_catalog(client, sqlite_session, account, role):
    account.role_code = role
    sqlite_session.commit()
    response = client.get(URL, headers=headers(account))
    assert response.status_code == 200
    assert response.json() == []


def test_returns_all_active_datasets_in_id_order(client, sqlite_session, account):
    first = add_dataset(sqlite_session, account, "zeta")
    add_dataset(sqlite_session, account, "inactive", active=False)
    last = add_dataset(sqlite_session, account, "alpha", row_count=40)
    response = client.get(URL, headers=headers(account))
    assert response.status_code == 200
    assert response.json() == [
        {"dataset_id": first.dataset_id, "name": "zeta", "row_count": 150},
        {"dataset_id": last.dataset_id, "name": "alpha", "row_count": 40},
    ]


def test_inactive_only_catalog_is_empty(client, sqlite_session, account):
    add_dataset(sqlite_session, account, "inactive", active=False)
    response = client.get(URL, headers=headers(account))
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("role", ["USER", "USER_PLUS"])
def test_non_manager_roles_are_forbidden(client, sqlite_session, account, role):
    account.role_code = role
    sqlite_session.commit()
    assert client.get(URL, headers=headers(account)).status_code == 403


@pytest.mark.parametrize("role", ["RESEARCHER", "DEVELOPER"])
def test_unverified_manager_is_forbidden(client, sqlite_session, account, role):
    account.role_code = role
    account.is_email_verified = False
    sqlite_session.commit()
    assert client.get(URL, headers=headers(account)).status_code == 403


@pytest.mark.parametrize("role", ["RESEARCHER", "DEVELOPER"])
def test_inactive_manager_is_rejected(client, sqlite_session, account, role):
    account.role_code = role
    account.is_active = False
    sqlite_session.commit()
    assert client.get(URL, headers=headers(account)).status_code == 401


def test_missing_credentials_are_rejected(client):
    assert client.get(URL).status_code in (401, 403)


def test_invalid_token_is_rejected(client):
    assert client.get(URL, headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_current_role_overrules_stale_privileged_token(client, sqlite_session, account):
    auth = headers(account, token_role="DEVELOPER")
    account.role_code = "USER"
    sqlite_session.commit()
    assert client.get(URL, headers=auth).status_code == 403


def test_current_role_allows_access_after_upgrade(client, account):
    assert client.get(URL, headers=headers(account, token_role="USER")).status_code == 200


def test_token_cannot_bypass_later_email_unverification(client, sqlite_session, account):
    auth = headers(account)
    account.is_email_verified = False
    sqlite_session.commit()
    assert client.get(URL, headers=auth).status_code == 403


def test_catalog_query_never_reads_csv_or_other_dataset_columns(
    client, sqlite_session, sqlite_engine, account,
):
    add_dataset(sqlite_session, account, "iris")
    statements = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.lower())

    event.listen(sqlite_engine, "before_cursor_execute", capture)
    try:
        response = client.get(URL, headers=headers(account))
    finally:
        event.remove(sqlite_engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    dataset_queries = [sql for sql in statements if "from main.dataset" in sql
                       or "from dataset" in sql]
    assert len(dataset_queries) == 1
    selected_columns = dataset_queries[0].split("from", 1)[0]
    assert "csv_file" not in selected_columns
    assert "csv_sha256" not in selected_columns
    assert "created_by" not in selected_columns
    assert set(response.json()[0]) == {"dataset_id", "name", "row_count"}
