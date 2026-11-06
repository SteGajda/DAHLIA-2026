"""Creation contract, persisted order and transaction rollback tests."""

import hashlib
from decimal import Decimal

from fastapi import HTTPException
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.security import create_access_token
from app.models.experiment import Dataset, PredefinedSet, PredefinedSetPoint
from app.models.user import AppUser
from app.schemas.predefined_set import PredefinedSetCreate
from app.services.predefined_set_authoring import create_predefined_set

URL = "/api/v1/predefined-sets"


@pytest.fixture
def author(sqlite_session):
    user = AppUser(email="author@example.com", display_name="Author",
                   password_hash="unused", role_code="RESEARCHER",
                   is_active=True, is_email_verified=True)
    sqlite_session.add(user)
    sqlite_session.commit()
    return user


def add_dataset(db, author, name="iris"):
    content = b"Id,value\n1,4.2\n"
    dataset = Dataset(
        name=name, csv_file_name=f"{name}.csv", csv_file=content,
        csv_sha256=hashlib.sha256(content).digest(), row_count=150,
        imputed_column="value", target_column=None,
        reference_columns_json="[]", categorical_columns_json="[]",
        precision_value=Decimal("0.1"), created_by=author.user_id, is_active=True,
    )
    db.add(dataset)
    db.commit()
    return dataset


@pytest.fixture
def dataset(sqlite_session, author):
    return add_dataset(sqlite_session, author)


def headers(author, role=None):
    return {"Authorization": "Bearer " + create_access_token(
        author.user_id, role or author.role_code,
    )}


def payload(dataset):
    return dict(dataset_id=dataset.dataset_id, na_fraction=0.2,
                removed_indices=list(range(29, -1, -1)),
                annotation_indices=list(range(14, -1, -1)))


def assert_no_sets(db):
    assert db.scalar(select(func.count()).select_from(PredefinedSet)) == 0
    assert db.scalar(select(func.count()).select_from(PredefinedSetPoint)) == 0


@pytest.mark.parametrize("role", ["RESEARCHER", "DEVELOPER"])
def test_create_persists_complete_definition(client, sqlite_session, author, dataset, role):
    author.role_code = role
    sqlite_session.commit()
    response = client.post(URL, headers=headers(author), json=payload(dataset))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["predefined_set_id"] > 0
    assert body["dataset_id"] == dataset.dataset_id
    assert body["na_fraction"] == 0.2
    assert body["is_active"] is True
    assert body["created_by"] == author.user_id
    assert body["created_at"]
    assert body["removed_indices"] == list(range(30))
    assert body["annotation_indices"] == list(range(14, -1, -1))
    saved = sqlite_session.get(PredefinedSet, body["predefined_set_id"])
    assert saved.name == f"Set #{saved.predefined_set_id}"
    assert saved.created_by == author.user_id
    assert saved.na_fraction == Decimal("0.2")
    points = sqlite_session.scalars(select(PredefinedSetPoint).where(
        PredefinedSetPoint.predefined_set_id == saved.predefined_set_id,
    )).all()
    assert len(points) == 30
    annotated = sorted((p for p in points if p.annotation_order is not None),
                       key=lambda p: p.annotation_order)
    assert [p.row_index for p in annotated] == body["annotation_indices"]
    assert [p.annotation_order for p in annotated] == list(range(1, 16))
    assert sum(p.annotation_order is None for p in points) == 15


@pytest.mark.parametrize("fraction,count", [(0.1, 15), (0.2, 30), (0.3, 45)])
def test_supported_fractions(client, author, dataset, fraction, count):
    data = payload(dataset)
    data.update(na_fraction=fraction, removed_indices=list(range(count)))
    response = client.post(URL, headers=headers(author), json=data)
    assert response.status_code == 201
    assert len(response.json()["removed_indices"]) == count


def test_repeated_definitions_get_new_ids_without_changing_old_set(
    client, sqlite_session, author, dataset,
):
    original = client.post(URL, headers=headers(author), json=payload(dataset)).json()
    data = payload(dataset)
    data["annotation_indices"].reverse()
    newer = client.post(URL, headers=headers(author), json=data)
    assert newer.status_code == 201
    assert newer.json()["predefined_set_id"] != original["predefined_set_id"]
    old = sqlite_session.get(PredefinedSet, original["predefined_set_id"])
    assert old.is_active is True
    points = sqlite_session.scalars(select(PredefinedSetPoint).where(
        PredefinedSetPoint.predefined_set_id == old.predefined_set_id,
        PredefinedSetPoint.annotation_order.is_not(None),
    ).order_by(PredefinedSetPoint.annotation_order)).all()
    assert [p.row_index for p in points] == original["annotation_indices"]


def test_row_positions_do_not_conflict_across_datasets(client, sqlite_session, author, dataset):
    other = add_dataset(sqlite_session, author, "other")
    ids = []
    for selected in (dataset, other):
        response = client.post(URL, headers=headers(author), json=payload(selected))
        assert response.status_code == 201
        assert response.json()["dataset_id"] == selected.dataset_id
        ids.append(response.json()["predefined_set_id"])
    assert len(set(ids)) == 2
    assert sqlite_session.scalar(select(func.count()).select_from(PredefinedSetPoint)) == 60


def test_exact_active_duplicate_is_rejected_even_if_removed_order_changes(client, sqlite_session, author, dataset):
    first = client.post(URL, headers=headers(author), json=payload(dataset)).json()
    data = payload(dataset)
    data["removed_indices"].reverse()
    response = client.post(URL, headers=headers(author), json=data)
    assert response.status_code == 409
    assert response.json()["detail"] == f"An identical active set already exists: Set #{first['predefined_set_id']}."
    assert sqlite_session.scalar(select(func.count()).select_from(PredefinedSet)) == 1
    assert sqlite_session.scalar(select(func.count()).select_from(PredefinedSetPoint)) == 30


def test_active_duplicate_is_rejected_across_authors(client, sqlite_session, author, dataset):
    first = client.post(URL, headers=headers(author), json=payload(dataset)).json()
    other = AppUser(email="other@example.com", display_name="Other", password_hash="unused",
                    role_code="DEVELOPER", is_active=True, is_email_verified=True)
    sqlite_session.add(other)
    sqlite_session.commit()
    response = client.post(URL, headers=headers(other), json=payload(dataset))
    assert response.status_code == 409
    assert f"Set #{first['predefined_set_id']}" in response.json()["detail"]


def test_inactive_duplicate_allows_new_active_set_then_blocks_next_copy(client, sqlite_session, author, dataset):
    first = client.post(URL, headers=headers(author), json=payload(dataset)).json()
    old = sqlite_session.get(PredefinedSet, first["predefined_set_id"])
    old.is_active = False
    sqlite_session.commit()
    response = client.post(URL, headers=headers(author), json=payload(dataset))
    assert response.status_code == 201
    assert response.json()["is_active"] is True
    assert response.json()["predefined_set_id"] != old.predefined_set_id
    sqlite_session.refresh(old)
    assert old.is_active is False
    assert client.post(URL, headers=headers(author), json=payload(dataset)).status_code == 409


@pytest.mark.parametrize("change", ["removed", "fraction"])
def test_different_definition_can_be_saved(client, author, dataset, change):
    assert client.post(URL, headers=headers(author), json=payload(dataset)).status_code == 201
    data = payload(dataset)
    if change == "removed":
        data["removed_indices"] = list(range(29)) + [149]
    else:
        data.update(na_fraction=0.3, removed_indices=list(range(45)))
    assert client.post(URL, headers=headers(author), json=data).status_code == 201


def test_sqlserver_creation_locks_dataset_and_compiles_active_comparison(sqlite_session, author, dataset):
    from sqlalchemy import event
    from sqlalchemy.dialects import mssql

    statements = []
    def capture(conn, clause, multiparams, params, options):
        statements.append(str(clause.compile(dialect=mssql.dialect())))
    engine = sqlite_session.get_bind()
    event.listen(engine, "before_execute", capture)
    try:
        create_predefined_set(sqlite_session, PredefinedSetCreate(**payload(dataset)), author)
    finally:
        event.remove(engine, "before_execute", capture)
    assert any("WITH (UPDLOCK, HOLDLOCK)" in sql and "dahlia.dataset" in sql for sql in statements)
    assert any("predefined_set.is_active = 1" in sql for sql in statements)
    assert not any("is_active IS 1" in sql for sql in statements)


@pytest.mark.parametrize("role", ["USER", "USER_PLUS"])
def test_other_roles_cannot_create(client, sqlite_session, author, dataset, role):
    author.role_code = role
    sqlite_session.commit()
    response = client.post(URL, headers=headers(author), json=payload(dataset))
    assert response.status_code == 403
    assert_no_sets(sqlite_session)


@pytest.mark.parametrize("role", ["RESEARCHER", "DEVELOPER"])
@pytest.mark.parametrize("field,status", [("is_active", 401), ("is_email_verified", 403)])
def test_account_state_is_required(client, sqlite_session, author, dataset, role, field, status):
    author.role_code = role
    auth = headers(author)
    setattr(author, field, False)
    sqlite_session.commit()
    assert client.post(URL, headers=auth, json=payload(dataset)).status_code == status
    assert_no_sets(sqlite_session)


def test_no_credentials_cannot_create(client, sqlite_session, dataset):
    assert client.post(URL, json=payload(dataset)).status_code in (401, 403)
    assert_no_sets(sqlite_session)


def test_stale_role_claim_does_not_grant_creation(client, sqlite_session, author, dataset):
    auth = headers(author, role="DEVELOPER")
    author.role_code = "USER"
    sqlite_session.commit()
    assert client.post(URL, headers=auth, json=payload(dataset)).status_code == 403
    assert_no_sets(sqlite_session)


def test_unknown_dataset_returns_404(client, sqlite_session, author, dataset):
    data = payload(dataset)
    data["dataset_id"] = dataset.dataset_id + 100
    assert client.post(URL, headers=headers(author), json=data).status_code == 404
    assert_no_sets(sqlite_session)


def test_inactive_dataset_returns_409(client, sqlite_session, author, dataset):
    dataset.is_active = False
    sqlite_session.commit()
    assert client.post(URL, headers=headers(author), json=payload(dataset)).status_code == 409
    assert_no_sets(sqlite_session)


@pytest.mark.parametrize("field,value", [
    ("na_fraction", 0.15), ("na_fraction", "0.2"),
    ("dataset_id", True), ("dataset_id", "1"),
    ("removed_indices", list(range(29))),
    ("removed_indices", [0] * 30),
    ("removed_indices", [-1] + list(range(29))),
    ("removed_indices", list(range(29)) + [150]),
    ("removed_indices", [True] + list(range(1, 30))),
    ("removed_indices", [0.0] + list(range(1, 30))),
    ("annotation_indices", []), ("annotation_indices", list(range(7))),
    ("annotation_indices", list(range(16))),
    ("annotation_indices", [0] * 15),
    ("annotation_indices", list(range(14)) + [30]),
    ("annotation_indices", list(range(14)) + [150]),
    ("annotation_indices", list(range(14)) + ["14"]),
])
def test_invalid_definitions_never_save(client, sqlite_session, author, dataset, field, value):
    data = payload(dataset)
    data[field] = value
    assert client.post(URL, headers=headers(author), json=data).status_code == 422
    assert_no_sets(sqlite_session)


def test_too_small_dataset_cannot_create_set(client, sqlite_session, author, dataset):
    dataset.row_count = 40
    sqlite_session.commit()
    data = payload(dataset)
    data.update(na_fraction=0.3, removed_indices=list(range(12)))
    assert client.post(URL, headers=headers(author), json=data).status_code == 422
    assert_no_sets(sqlite_session)


@pytest.mark.parametrize("field,value", [
    ("name", "Manual name"), ("created_by", 999), ("is_active", False),
    ("seed", 42), ("predefined_set_id", 123),
])
def test_client_cannot_override_server_fields(client, sqlite_session, author, dataset, field, value):
    data = payload(dataset)
    data[field] = value
    assert client.post(URL, headers=headers(author), json=data).status_code == 422
    assert_no_sets(sqlite_session)


@pytest.mark.parametrize("failure_at", ["flush", "commit"])
@pytest.mark.parametrize("constraint_failure", [False, True])
def test_database_failure_rolls_back_set_and_all_points(
    sqlite_session, author, dataset, monkeypatch, failure_at, constraint_failure,
):
    error = (IntegrityError("private database detail", {}, Exception("private detail"))
             if constraint_failure else SQLAlchemyError("private database detail"))
    original_flush = sqlite_session.flush
    calls = 0

    def failing_flush(*args, **kwargs):
        nonlocal calls
        original_flush(*args, **kwargs)
        calls += 1
        if calls == 2:
            # Both parent and child rows reached the DB but are uncommitted.
            raise error

    def failing_commit():
        raise error

    if failure_at == "flush":
        monkeypatch.setattr(sqlite_session, "flush", failing_flush)
    else:
        monkeypatch.setattr(sqlite_session, "commit", failing_commit)
    with pytest.raises(HTTPException) as caught:
        create_predefined_set(sqlite_session, PredefinedSetCreate(**payload(dataset)), author)
    assert caught.value.status_code == (409 if constraint_failure else 500)
    assert "private" not in caught.value.detail
    assert_no_sets(sqlite_session)
    assert sqlite_session.get(Dataset, dataset.dataset_id) is not None


@pytest.mark.parametrize("role", ["RESEARCHER", "DEVELOPER"])
def test_deactivate_other_authors_set_preserves_definition_and_is_idempotent(client, sqlite_session, author, dataset, role):
    original = client.post(URL, headers=headers(author), json=payload(dataset)).json()
    manager = AppUser(email="manager@example.com", display_name="Manager", password_hash="unused",
                      role_code=role, is_active=True, is_email_verified=True)
    sqlite_session.add(manager)
    sqlite_session.commit()
    url = f"{URL}/{original['predefined_set_id']}/deactivate"
    for _ in range(2):
        response = client.post(url, headers=headers(manager))
        assert response.status_code == 200
        assert response.json() == dict(predefined_set_id=original["predefined_set_id"], is_active=False)
    detail = client.get(f"{URL}/{original['predefined_set_id']}", headers=headers(manager)).json()
    assert detail == {**original, "is_active": False}
    assert sqlite_session.scalar(select(func.count()).select_from(PredefinedSetPoint)) == 30
    assert client.get(URL, headers=headers(manager)).json()[0]["is_active"] is False
    # Deactivation permits a new identical definition, never reactivates the old ID.
    created = client.post(URL, headers=headers(manager), json=payload(dataset))
    assert created.status_code == 201
    assert created.json()["predefined_set_id"] != original["predefined_set_id"]


@pytest.mark.parametrize("state,status", [("USER", 403), ("USER_PLUS", 403), ("inactive", 401), ("unverified", 403), ("anonymous", 401)])
def test_deactivation_requires_verified_active_manager(client, sqlite_session, author, dataset, state, status):
    saved = client.post(URL, headers=headers(author), json=payload(dataset)).json()
    auth = headers(author)
    if state in ("USER", "USER_PLUS"):
        author.role_code = state
    elif state == "inactive":
        author.is_active = False
    elif state == "unverified":
        author.is_email_verified = False
    else:
        auth = {}
    sqlite_session.commit()
    response = client.post(f"{URL}/{saved['predefined_set_id']}/deactivate", headers=auth)
    assert response.status_code == status
    sqlite_session.expire_all()
    assert sqlite_session.get(PredefinedSet, saved["predefined_set_id"]).is_active is True


@pytest.mark.parametrize("set_id,status", [(999, 404), (0, 422), (-1, 422), ("abc", 422)])
def test_deactivate_unknown_or_invalid_id(client, author, set_id, status):
    assert client.post(f"{URL}/{set_id}/deactivate", headers=headers(author)).status_code == status


def test_deactivation_failure_rolls_back(sqlite_session, author, dataset, monkeypatch):
    from app.services.predefined_set_authoring import deactivate_predefined_set
    saved = create_predefined_set(sqlite_session, PredefinedSetCreate(**payload(dataset)), author)
    def fail():
        raise SQLAlchemyError("private connection details")
    monkeypatch.setattr(sqlite_session, "commit", fail)
    with pytest.raises(HTTPException) as caught:
        deactivate_predefined_set(sqlite_session, saved.predefined_set_id)
    assert caught.value.status_code == 500
    assert "private" not in caught.value.detail
    assert sqlite_session.get(PredefinedSet, saved.predefined_set_id).is_active is True
