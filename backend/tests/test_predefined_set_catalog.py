"""Management reads preserve definitions, ownership and inactive history."""

import hashlib
from decimal import Decimal

import pytest
from sqlalchemy import event, select

from app.core.security import create_access_token
from app.models.experiment import Dataset, PredefinedSet, PredefinedSetPoint
from app.models.user import AppUser
from app.schemas.predefined_set import PredefinedSetCreate
from app.services.predefined_set_authoring import create_predefined_set

URL = "/api/v1/predefined-sets"


@pytest.fixture
def manager(sqlite_session):
    user = AppUser(email="reader@example.com", display_name="Manager",
                   password_hash="unused", role_code="RESEARCHER",
                   is_active=True, is_email_verified=True)
    sqlite_session.add(user)
    sqlite_session.commit()
    return user


def headers(manager, role=None):
    return {"Authorization": "Bearer " + create_access_token(
        manager.user_id, role or manager.role_code,
    )}


@pytest.fixture
def definitions(sqlite_session, manager):
    other = AppUser(email="other-author@example.com", display_name="Other author",
                    password_hash="unused", role_code="RESEARCHER",
                    is_active=True, is_email_verified=True)
    sqlite_session.add(other)
    sqlite_session.flush()
    content = b"Id,value\n1,4.2\n"
    dataset = Dataset(
        name="iris", csv_file_name="iris.csv", csv_file=content,
        csv_sha256=hashlib.sha256(content).digest(), row_count=150,
        imputed_column="value", target_column=None,
        reference_columns_json="[]", categorical_columns_json="[]",
        precision_value=Decimal("0.1"), created_by=manager.user_id, is_active=True,
    )
    sqlite_session.add(dataset)
    sqlite_session.commit()
    payload = PredefinedSetCreate(
        dataset_id=dataset.dataset_id, na_fraction=0.2,
        removed_indices=list(range(29, -1, -1)),
        annotation_indices=[21, 2, 29, 0, 14, 7, 9, 8, 11, 10, 18, 16, 3, 22, 5],
    )
    first = create_predefined_set(sqlite_session, payload, manager)
    # The catalog contains distinct definitions; active duplicates are rejected.
    second_payload = payload.model_copy(update={"annotation_indices": list(reversed(payload.annotation_indices))})
    second = create_predefined_set(sqlite_session, second_payload, other)
    saved = sqlite_session.get(PredefinedSet, second.predefined_set_id)
    saved.is_active = False
    sqlite_session.commit()
    return first, second


def test_empty_catalog(client, manager):
    response = client.get(URL, headers=headers(manager))
    assert response.status_code == 200
    assert response.json() == []


def test_list_includes_all_authors_and_states_in_id_order(client, manager, definitions):
    first, second = definitions
    response = client.get(URL, headers=headers(manager))
    assert response.status_code == 200
    rows = response.json()
    assert [row["predefined_set_id"] for row in rows] == [
        first.predefined_set_id, second.predefined_set_id,
    ]
    assert [row["created_by"] for row in rows] == [first.created_by, second.created_by]
    assert [row["is_active"] for row in rows] == [True, False]
    for row in rows:
        assert row["dataset_id"] == first.dataset_id
        assert row["dataset_name"] == "iris"
        assert row["na_fraction"] == 0.2
        assert row["created_at"]
        assert set(row) == {"predefined_set_id", "dataset_id", "dataset_name",
                            "na_fraction", "created_by", "created_at", "is_active"}


@pytest.mark.parametrize("index", [0, 1])
def test_detail_preserves_saved_points_and_order(client, manager, definitions, index):
    saved = definitions[index]
    expected = saved.model_dump(mode="json")
    expected["is_active"] = index == 0
    response = client.get(f"{URL}/{saved.predefined_set_id}", headers=headers(manager))
    assert response.status_code == 200
    assert response.json() == expected


def test_inactive_dataset_does_not_hide_management_history(
    client, sqlite_session, manager, definitions,
):
    first, _ = definitions
    dataset = sqlite_session.get(Dataset, first.dataset_id)
    dataset.is_active = False
    sqlite_session.commit()
    assert len(client.get(URL, headers=headers(manager)).json()) == 2
    assert client.get(f"{URL}/{first.predefined_set_id}", headers=headers(manager)).status_code == 200


@pytest.mark.parametrize("suffix", ["", "/1"])
@pytest.mark.parametrize("role", ["RESEARCHER", "DEVELOPER"])
def test_both_manager_roles_can_read(client, sqlite_session, manager, definitions, role, suffix):
    manager.role_code = role
    sqlite_session.commit()
    assert client.get(URL + suffix, headers=headers(manager)).status_code == 200


@pytest.mark.parametrize("suffix", ["", "/1"])
@pytest.mark.parametrize("role", ["USER", "USER_PLUS"])
def test_other_roles_are_forbidden(client, sqlite_session, manager, definitions, role, suffix):
    manager.role_code = role
    sqlite_session.commit()
    assert client.get(URL + suffix, headers=headers(manager)).status_code == 403


@pytest.mark.parametrize("suffix", ["", "/1"])
@pytest.mark.parametrize("field,status", [("is_active", 401), ("is_email_verified", 403)])
def test_account_state_is_required(client, sqlite_session, manager, definitions, field, status, suffix):
    auth = headers(manager)
    setattr(manager, field, False)
    sqlite_session.commit()
    assert client.get(URL + suffix, headers=auth).status_code == status


@pytest.mark.parametrize("suffix", ["", "/1"])
def test_anonymous_access_is_rejected(client, suffix):
    assert client.get(URL + suffix).status_code in (401, 403)


@pytest.mark.parametrize("suffix", ["", "/1"])
def test_stale_role_claim_does_not_grant_read_access(
    client, sqlite_session, manager, definitions, suffix,
):
    auth = headers(manager, role="DEVELOPER")
    manager.role_code = "USER"
    sqlite_session.commit()
    assert client.get(URL + suffix, headers=auth).status_code == 403


def test_unknown_set_returns_404(client, manager):
    assert client.get(f"{URL}/999", headers=headers(manager)).status_code == 404


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_invalid_set_id_returns_422(client, manager, value):
    assert client.get(f"{URL}/{value}", headers=headers(manager)).status_code == 422


@pytest.mark.parametrize("corruption", ["missing", "duplicate"])
def test_invalid_stored_order_is_reported_without_repair(
    client, sqlite_session, manager, definitions, corruption,
):
    first, _ = definitions
    point = sqlite_session.scalar(select(PredefinedSetPoint).where(
        PredefinedSetPoint.predefined_set_id == first.predefined_set_id,
        PredefinedSetPoint.annotation_order == 1,
    ))
    point.annotation_order = {"missing": None, "duplicate": 2}[corruption]
    sqlite_session.commit()
    response = client.get(f"{URL}/{first.predefined_set_id}", headers=headers(manager))
    assert response.status_code == 500
    assert response.json()["detail"] == "Stored predefined set has invalid annotation order."
    sqlite_session.refresh(point)
    assert point.annotation_order == {"missing": None, "duplicate": 2}[corruption]


def test_reads_do_not_write_and_list_does_not_load_points_or_csv(
    client, sqlite_engine, manager, definitions,
):
    first, _ = definitions
    statements = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.lower().strip())

    event.listen(sqlite_engine, "before_cursor_execute", capture)
    try:
        assert client.get(URL, headers=headers(manager)).status_code == 200
        list_statements = list(statements)
        path = f"{URL}/{first.predefined_set_id}"
        first_read = client.get(path, headers=headers(manager))
        second_read = client.get(path, headers=headers(manager))
        assert first_read.json() == second_read.json()
    finally:
        event.remove(sqlite_engine, "before_cursor_execute", capture)
    assert not any(sql.startswith(("insert ", "update ", "delete ")) for sql in statements)
    assert not any("predefined_set_point" in sql for sql in list_statements)
    assert not any("csv_file" in sql for sql in statements)


def test_public_selection_excludes_inactive_sets_and_private_metadata(client, manager, definitions):
    first, _ = definitions
    response = client.get(f"{URL}/available")
    assert response.status_code == 200
    assert response.json() == [dict(predefined_set_id=first.predefined_set_id,
        dataset_id=first.dataset_id, dataset_name="iris", na_fraction=0.2, is_active=True)]
    # Public read does not grant access to the management catalog or detail.
    assert client.get(URL).status_code in (401, 403)
    assert client.get(f"{URL}/{first.predefined_set_id}").status_code in (401, 403)
    assert client.post(f"{URL}/{first.predefined_set_id}/deactivate").status_code in (401, 403)


def test_public_selection_excludes_inactive_dataset(client, sqlite_session, manager, definitions):
    first, _ = definitions
    sqlite_session.get(Dataset, first.dataset_id).is_active = False
    sqlite_session.commit()
    assert client.get(f"{URL}/available").json() == []


def test_public_selection_refresh_removes_deactivated_set(client, manager, definitions):
    first, _ = definitions
    assert len(client.get(f"{URL}/available").json()) == 1
    assert client.post(f"{URL}/{first.predefined_set_id}/deactivate", headers=headers(manager)).status_code == 200
    assert client.get(f"{URL}/available").json() == []


def test_public_selection_sqlserver_comparisons(client, sqlite_engine, definitions):
    from sqlalchemy.dialects import mssql
    statements = []
    def capture(_conn, clause, _multiparams, _params, _options):
        statements.append(str(clause.compile(dialect=mssql.dialect())))
    event.listen(sqlite_engine, "before_execute", capture)
    try:
        assert client.get(f"{URL}/available").status_code == 200
    finally:
        event.remove(sqlite_engine, "before_execute", capture)
    assert len(statements) == 1
    assert "predefined_set.is_active = 1" in statements[0]
    assert "dataset.is_active = 1" in statements[0]
    assert "csv_file" not in statements[0]


def test_public_execution_package_contains_exact_points_and_checked_csv(client, definitions):
    import base64
    first, _ = definitions
    response = client.get(f"{URL}/{first.predefined_set_id}/execution")
    assert response.status_code == 200
    data = response.json()
    assert data['removed_indices'] == first.removed_indices
    assert data['annotation_indices'] == first.annotation_indices
    assert hashlib.sha256(base64.b64decode(data['csv_base64'])).hexdigest() == data['csv_sha256']
    assert 'created_by' not in data and 'created_at' not in data


def test_inactive_execution_package_is_rejected(client, manager, definitions):
    _, inactive = definitions
    assert client.get(f"{URL}/{inactive.predefined_set_id}/execution").status_code == 409
    assert client.get(f"{URL}/999/execution").status_code == 404


def test_execution_package_rejects_inactive_or_corrupt_dataset(client, sqlite_session, definitions):
    first, _ = definitions
    dataset = sqlite_session.get(Dataset, first.dataset_id)
    dataset.is_active = False
    sqlite_session.commit()
    assert client.get(f"{URL}/{first.predefined_set_id}/execution").status_code == 409
    dataset.is_active = True
    dataset.csv_file = b'changed'
    sqlite_session.commit()
    assert client.get(f"{URL}/{first.predefined_set_id}/execution").status_code == 500


def test_offline_catalog_identity_matches_package_and_survives_deactivation(client, manager, definitions):
    first, _ = definitions
    response = client.get(f"{URL}/offline-catalog")
    assert response.status_code == 200
    data = response.json()
    assert len(data['catalog_id']) == 64
    assert [item['predefined_set_id'] for item in data['sets']] == [first.predefined_set_id]
    package = client.get(f"{URL}/{first.predefined_set_id}/execution").json()
    assert package['catalog_id'] == data['catalog_id']
    assert 'created_by' not in data['sets'][0] and 'csv_base64' not in data['sets'][0]
    assert client.post(f"{URL}/{first.predefined_set_id}/deactivate", headers=headers(manager)).status_code == 200
    assert client.get(f"{URL}/offline-catalog").json() == dict(catalog_id=data['catalog_id'], sets=[])


def test_catalog_identity_distinguishes_sql_server_and_database():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.services.predefined_set_catalog import get_catalog_id
    db = Mock()
    db.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name='mssql'))
    db.execute.return_value.one.return_value = ('local-server', 'DAHLIA_DEV')
    local = get_catalog_id(db)
    assert get_catalog_id(db) == local
    db.execute.return_value.one.return_value = ('azure-server', 'DAHLIA_DEV')
    assert get_catalog_id(db) != local
    db.execute.return_value.one.return_value = ('local-server', 'DAHLIA')
    assert get_catalog_id(db) != local
