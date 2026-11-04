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
