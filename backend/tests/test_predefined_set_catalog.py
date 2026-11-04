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
    second = create_predefined_set(sqlite_session, payload, other)
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
