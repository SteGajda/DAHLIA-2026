"""Admin endpoint tests.

Covers GET/POST /api/v1/admin/role-requests and approve/reject actions.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.security import create_access_token, hash_password
from app.models.user import AppUser, RoleRequest

_BASE = "/api/v1"
_AUTH = f"{_BASE}/auth"
_ADMIN = f"{_BASE}/admin"


def _make_user(db, email: str, role: str = "USER") -> AppUser:
    user = AppUser(
        email=email,
        display_name=email.split("@")[0],
        password_hash=hash_password("pass1234"),
        role_code=role,
        is_pw_affiliated=False,
        consent_given=True,
        is_email_verified=True,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user: AppUser) -> dict:
    token = create_access_token(user.user_id, user.role_code)
    return {"Authorization": f"Bearer {token}"}


def _make_role_request(db, user: AppUser, role: str = "USER_PLUS") -> RoleRequest:
    req = RoleRequest(
        user_id=user.user_id,
        requested_role=role,
        status="PENDING",
        created_at=datetime.now(timezone.utc),
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


class TestListRoleRequests:
    def test_developer_sees_pending_requests(self, client, sqlite_session):
        user = _make_user(sqlite_session, "alice@x.com")
        dev = _make_user(sqlite_session, "dev@x.com", "DEVELOPER")
        _make_role_request(sqlite_session, user)

        resp = client.get(f"{_ADMIN}/role-requests", headers=_headers(dev))
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["requested_role"] == "USER_PLUS"

    def test_non_developer_gets_403(self, client, sqlite_session):
        user = _make_user(sqlite_session, "alice@x.com", "RESEARCHER")
        resp = client.get(f"{_ADMIN}/role-requests", headers=_headers(user))
        assert resp.status_code == 403

    def test_unauthenticated_gets_401(self, client):
        resp = client.get(f"{_ADMIN}/role-requests")
        assert resp.status_code == 403 or resp.status_code == 401

    def test_empty_when_no_pending(self, client, sqlite_session):
        dev = _make_user(sqlite_session, "dev@x.com", "DEVELOPER")
        resp = client.get(f"{_ADMIN}/role-requests", headers=_headers(dev))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_approved_requests_not_listed(self, client, sqlite_session):
        user = _make_user(sqlite_session, "alice@x.com")
        dev = _make_user(sqlite_session, "dev@x.com", "DEVELOPER")
        req = _make_role_request(sqlite_session, user)
        req.status = "APPROVED"
        sqlite_session.commit()

        resp = client.get(f"{_ADMIN}/role-requests", headers=_headers(dev))
        assert resp.json() == []


class TestApproveRoleRequest:
    def test_approve_sets_user_role(self, client, sqlite_session):
        user = _make_user(sqlite_session, "alice@x.com")
        dev = _make_user(sqlite_session, "dev@x.com", "DEVELOPER")
        req = _make_role_request(sqlite_session, user)

        resp = client.post(f"{_ADMIN}/role-requests/{req.request_id}/approve", headers=_headers(dev))
        assert resp.status_code == 200
        assert resp.json()["new_status"] == "APPROVED"

        sqlite_session.refresh(user)
        assert user.role_code == "USER_PLUS"

    def test_approve_records_reviewer(self, client, sqlite_session):
        user = _make_user(sqlite_session, "alice@x.com")
        dev = _make_user(sqlite_session, "dev@x.com", "DEVELOPER")
        req = _make_role_request(sqlite_session, user)

        client.post(f"{_ADMIN}/role-requests/{req.request_id}/approve", headers=_headers(dev))

        sqlite_session.refresh(req)
        assert req.reviewed_by == dev.user_id
        assert req.reviewed_at is not None

    def test_approve_nonexistent_returns_404(self, client, sqlite_session):
        dev = _make_user(sqlite_session, "dev@x.com", "DEVELOPER")
        resp = client.post(f"{_ADMIN}/role-requests/9999/approve", headers=_headers(dev))
        assert resp.status_code == 404

    def test_approve_already_approved_returns_404(self, client, sqlite_session):
        user = _make_user(sqlite_session, "alice@x.com")
        dev = _make_user(sqlite_session, "dev@x.com", "DEVELOPER")
        req = _make_role_request(sqlite_session, user)
        req.status = "APPROVED"
        sqlite_session.commit()

        resp = client.post(f"{_ADMIN}/role-requests/{req.request_id}/approve", headers=_headers(dev))
        assert resp.status_code == 404

    def test_non_developer_cannot_approve(self, client, sqlite_session):
        user = _make_user(sqlite_session, "alice@x.com")
        researcher = _make_user(sqlite_session, "res@x.com", "RESEARCHER")
        req = _make_role_request(sqlite_session, user)

        resp = client.post(f"{_ADMIN}/role-requests/{req.request_id}/approve", headers=_headers(researcher))
        assert resp.status_code == 403


class TestRejectRoleRequest:
    def test_reject_sets_status(self, client, sqlite_session):
        user = _make_user(sqlite_session, "alice@x.com")
        dev = _make_user(sqlite_session, "dev@x.com", "DEVELOPER")
        req = _make_role_request(sqlite_session, user)

        resp = client.post(f"{_ADMIN}/role-requests/{req.request_id}/reject", headers=_headers(dev))
        assert resp.status_code == 200
        assert resp.json()["new_status"] == "REJECTED"

        sqlite_session.refresh(req)
        assert req.status == "REJECTED"

    def test_reject_does_not_change_user_role(self, client, sqlite_session):
        user = _make_user(sqlite_session, "alice@x.com")
        dev = _make_user(sqlite_session, "dev@x.com", "DEVELOPER")
        req = _make_role_request(sqlite_session, user)

        client.post(f"{_ADMIN}/role-requests/{req.request_id}/reject", headers=_headers(dev))

        sqlite_session.refresh(user)
        assert user.role_code == "USER"

    def test_reject_nonexistent_returns_404(self, client, sqlite_session):
        dev = _make_user(sqlite_session, "dev@x.com", "DEVELOPER")
        resp = client.post(f"{_ADMIN}/role-requests/9999/reject", headers=_headers(dev))
        assert resp.status_code == 404

    def test_non_developer_cannot_reject(self, client, sqlite_session):
        user = _make_user(sqlite_session, "alice@x.com")
        researcher = _make_user(sqlite_session, "res@x.com", "RESEARCHER")
        req = _make_role_request(sqlite_session, user)

        resp = client.post(f"{_ADMIN}/role-requests/{req.request_id}/reject", headers=_headers(researcher))
        assert resp.status_code == 403
