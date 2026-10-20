"""Real route flow with SMTP replaced at its network boundary."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from urllib.parse import urlsplit

import jwt
import pytest
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.dialects import mssql

from app.core.config import Settings, get_settings
from app.core.security import create_access_token, create_email_verification_token, decode_token
from app.models.user import AppUser
from app.services import verification_email as mail


@pytest.fixture()
def delivery(monkeypatch):
    messages = []
    monkeypatch.setattr(mail, "send_verification_email", lambda email, token: messages.append((email, token)))
    return messages


def register(client):
    return client.post("/api/v1/auth/register", json={
        "email": "verify@example.com", "display_name": "Verify",
        "password": "Password123!", "is_pw_affiliated": False, "consent_given": True,
    })


def headers(user_id):
    return {"Authorization": "Bearer " + create_access_token(user_id, "USER")}


def test_registration_delivers_bound_token_without_leaking_it(client, sqlite_session, delivery, caplog):
    response = register(client)
    assert response.status_code == 201 and response.json()["email_sent"] is True
    email, token = delivery[0]
    assert email == "verify@example.com"
    claims = decode_token(token)
    assert claims["email"] == email and claims["purpose"] == "email_verify"
    assert token not in response.text and token not in caplog.text
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    me = client.get("/api/v1/auth/me", headers=headers(response.json()["user_id"]))
    assert me.json()["is_email_verified"] is True
    # No further message for an already verified account.
    result = client.post("/api/v1/auth/resend-verification", headers=headers(response.json()["user_id"]))
    assert result.status_code == 200 and result.json()["email_sent"] is False
    assert len(delivery) == 1


def test_resend_requires_auth_and_cannot_choose_another_recipient(client, sqlite_session, delivery):
    response = register(client)
    uid = response.json()["user_id"]
    assert client.post("/api/v1/auth/resend-verification").status_code in (401, 403)
    retry = client.post("/api/v1/auth/resend-verification", headers=headers(uid))
    assert retry.status_code == 429 and retry.headers["retry-after"] == "60"
    user = sqlite_session.get(AppUser, uid)
    user.email_verification_sent_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    sqlite_session.commit()
    retry = client.post("/api/v1/auth/resend-verification", headers=headers(uid), json={"email": "other@example.com"})
    assert retry.status_code == 200
    assert delivery[-1][0] == "verify@example.com"
    assert len(delivery) == 2


def test_smtp_failure_keeps_account_unverified_and_does_not_expose_provider_error(client, sqlite_session, monkeypatch, caplog):
    def fail(*args):
        raise mail.EmailDeliveryError("private-provider-response")
    monkeypatch.setattr(mail, "send_verification_email", fail)
    response = register(client)
    assert response.status_code == 201 and response.json()["email_sent"] is False
    uid = response.json()["user_id"]
    user = sqlite_session.get(AppUser, uid)
    assert not user.is_email_verified
    user.email_verification_sent_at = None
    sqlite_session.commit()
    response = client.post("/api/v1/auth/resend-verification", headers=headers(uid))
    assert response.status_code == 503
    assert "private-provider-response" not in response.text + caplog.text
    assert client.post("/api/v1/auth/resend-verification", headers=headers(uid)).status_code == 429


def test_link_page_has_no_state_change_and_hides_token_from_requests(client, sqlite_session, delivery):
    uid = register(client).json()["user_id"]
    response = client.get("/api/v1/auth/verify-email")
    assert response.status_code == 200
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "window.location.hash" in response.text
    assert "button.addEventListener('click'" in response.text
    assert not sqlite_session.get(AppUser, uid).is_email_verified


def test_changed_email_missing_expiry_and_cross_purpose_tokens_are_rejected(client, sqlite_session, delivery):
    uid = register(client).json()["user_id"]
    original = delivery[0][1]
    user = sqlite_session.get(AppUser, uid)
    user.email = "changed@example.com"
    sqlite_session.commit()
    assert client.post("/api/v1/auth/verify-email", json={"token": original}).status_code == 400
    missing_exp = jwt.encode({"sub": str(uid), "purpose": "email_verify"}, get_settings().SECRET_KEY, algorithm="HS256")
    for token in (missing_exp, create_access_token(uid, "USER")):
        assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400
    token = create_email_verification_token(uid, user.email)
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_smtp_uses_verified_tls_and_fragment_link(monkeypatch):
    settings = Settings(_env_file=None, SECRET_KEY="test-key", EMAIL_DELIVERY_MODE="smtp",
                        PUBLIC_API_URL="https://api.example.com", SMTP_USERNAME="sender@gmail.com",
                        SMTP_FROM_EMAIL="sender@gmail.com", SMTP_PASSWORD="app-password")
    monkeypatch.setattr(mail, "get_settings", lambda: settings)
    smtp = MagicMock()
    smtp.send_message.return_value = {}
    factory = MagicMock()
    factory.return_value.__enter__.return_value = smtp
    monkeypatch.setattr(mail.smtplib, "SMTP", factory)
    mail.send_verification_email("recipient@example.com", "secret-token")
    context = smtp.starttls.call_args.kwargs["context"]
    assert context.check_hostname is True
    smtp.login.assert_called_once_with("sender@gmail.com", "app-password")
    message = smtp.send_message.call_args.args[0]
    link = next(line for line in message.get_content().splitlines() if line.startswith("https://"))
    assert urlsplit(link).fragment == "token=secret-token"
    assert not urlsplit(link).query
    assert message["To"] == "recipient@example.com"
    assert "app-password" not in str(settings)


def test_disabled_delivery_and_missing_starttls_never_send(monkeypatch):
    settings = Settings(_env_file=None, SECRET_KEY="test-key")
    monkeypatch.setattr(mail, "get_settings", lambda: settings)
    factory = MagicMock()
    monkeypatch.setattr(mail.smtplib, "SMTP", factory)
    with pytest.raises(mail.EmailDeliveryError):
        mail.send_verification_email("recipient@example.com", "token")
    factory.assert_not_called()
    settings.EMAIL_DELIVERY_MODE = "smtp"
    smtp = factory.return_value.__enter__.return_value
    smtp.starttls.side_effect = mail.smtplib.SMTPNotSupportedError("no TLS")
    with pytest.raises(mail.EmailDeliveryError):
        mail.send_verification_email("recipient@example.com", "token")
    smtp.login.assert_not_called()
    smtp.send_message.assert_not_called()


@pytest.mark.parametrize("url", ["http://example.com", "https://user:pass@example.com", "https://example.com/path", "https://example.com?token=x"])
def test_unsafe_public_origin_is_rejected(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY="test", EMAIL_DELIVERY_MODE="smtp", PUBLIC_API_URL=url,
                 SMTP_USERNAME="sender", SMTP_PASSWORD="secret")


def test_cooldown_boolean_predicates_compile_for_mssql():
    statement = update(AppUser).where(AppUser.is_active == True, AppUser.is_email_verified == False)
    sql = str(statement.values(email_verification_sent_at=None).compile(dialect=mssql.dialect()))
    assert "IS 0" not in sql and "IS 1" not in sql
    assert "is_email_verified = 0" in sql and "is_active = 1" in sql


def test_invalid_settings_do_not_print_smtp_password():
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, SECRET_KEY="test", EMAIL_DELIVERY_MODE="smtp",
                 PUBLIC_API_URL="http://example.com", SMTP_USERNAME="sender",
                 SMTP_PASSWORD="private-smtp-secret")
    assert "private-smtp-secret" not in str(error.value)
