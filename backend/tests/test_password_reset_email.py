"""Password reset uses the real mail path with only SMTP networking mocked."""

import logging
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest

from app.core.config import Settings
from app.core.security import decode_token, hash_password, verify_password
from app.models.user import AppUser
from app.services import verification_email as mail


@pytest.fixture()
def sender(monkeypatch):
    settings = Settings(
        _env_file=None, SECRET_KEY="isolated-test-key",
        EMAIL_DELIVERY_MODE="smtp", PUBLIC_API_URL="https://api.example.com",
        SMTP_USERNAME="sender@gmail.com", SMTP_FROM_EMAIL="sender@gmail.com",
        SMTP_PASSWORD="private-smtp-password",
    )
    monkeypatch.setattr(mail, "get_settings", lambda: settings)
    smtp = MagicMock()
    smtp.send_message.return_value = {}
    factory = MagicMock()
    factory.return_value.__enter__.return_value = smtp
    monkeypatch.setattr(mail.smtplib, "SMTP", factory)
    return settings, smtp, factory


@pytest.fixture()
def account(sqlite_session):
    user = AppUser(
        email="reset@example.com", display_name="Reset test",
        password_hash=hash_password("OldPassword123!"),
        is_active=True, is_email_verified=True,
    )
    sqlite_session.add(user)
    sqlite_session.commit()
    return user


def request_reset(client, email="reset@example.com"):
    return client.post("/api/v1/auth/forgot-password", json={"email": email})


def test_reset_email_link_changes_password_and_preserves_verification(
    client, sqlite_session, account, sender, caplog,
):
    settings, smtp, factory = sender
    caplog.set_level(logging.INFO)
    response = request_reset(client)
    assert response.status_code == 200
    factory.assert_called_once_with(settings.SMTP_HOST, settings.SMTP_PORT,
                                    timeout=settings.SMTP_TIMEOUT_SECONDS)
    assert smtp.starttls.call_args.kwargs["context"].check_hostname is True
    smtp.login.assert_called_once_with("sender@gmail.com", "private-smtp-password")
    message = smtp.send_message.call_args.args[0]
    assert message["From"] == "DAHLIA <sender@gmail.com>"
    assert message["To"] == account.email
    assert message["Subject"] == "Reset your DAHLIA password"
    body = message.get_content()
    assert "15 minutes" in body and "1 hour" not in body
    link = next(line for line in body.splitlines() if line.startswith("https://"))
    parts = urlsplit(link)
    assert parts.netloc == "api.example.com"
    assert parts.path == "/api/v1/auth/reset-password" and not parts.query
    token = parse_qs(parts.fragment)["token"][0]
    claims = decode_token(token)
    assert claims["purpose"] == "password_reset"
    assert claims["sub"] == str(account.user_id)
    assert claims["exp"] - claims["iat"] == 15 * 60
    assert token not in response.text + caplog.text
    assert "MOCK-SMTP" not in caplog.text
    assert "Password reset email submitted to SMTP." in caplog.text
    assert "private-smtp-password" not in caplog.text

    page = client.get(parts.path)
    assert page.status_code == 200 and page.headers["cache-control"] == "no-store"
    assert "window.location.hash" in page.text
    sqlite_session.refresh(account)
    assert verify_password("OldPassword123!", account.password_hash)
    # A reset link must not be accepted for registration email verification.
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400
    result = client.post(parts.path, json={"token": token, "new_password": "NewPassword123!"})
    assert result.status_code == 200
    sqlite_session.refresh(account)
    assert account.is_email_verified is True
    assert verify_password("NewPassword123!", account.password_hash)
    old = client.post("/api/v1/auth/login", json={"email": account.email, "password": "OldPassword123!"})
    new = client.post("/api/v1/auth/login", json={"email": account.email, "password": "NewPassword123!"})
    assert old.status_code == 401 and new.status_code == 200


@pytest.mark.parametrize("failure", ["disabled", "connection", "tls", "refused"])
def test_delivery_failure_is_logged_without_secrets_or_account_disclosure(
    client, sqlite_session, account, sender, caplog, failure,
):
    settings, smtp, factory = sender
    if failure == "disabled":
        settings.EMAIL_DELIVERY_MODE = "disabled"
    elif failure == "connection":
        factory.side_effect = OSError("private-provider-response")
    elif failure == "tls":
        smtp.starttls.side_effect = mail.smtplib.SMTPNotSupportedError("private-provider-response")
    else:
        smtp.send_message.return_value = {account.email: (550, b"private-provider-response")}
    response = request_reset(client)
    unknown = request_reset(client, "unknown@example.com")
    assert response.status_code == unknown.status_code == 200
    assert response.json() == unknown.json()
    assert "could not be submitted to SMTP" in caplog.text
    assert "private-provider-response" not in caplog.text + response.text
    assert "private-smtp-password" not in caplog.text + response.text
    assert account.email not in caplog.text
    sqlite_session.refresh(account)
    assert verify_password("OldPassword123!", account.password_hash)
    if failure == "disabled":
        factory.assert_not_called()
    if failure == "tls":
        smtp.login.assert_not_called()
        smtp.send_message.assert_not_called()


def test_unknown_and_inactive_accounts_do_not_send(client, sqlite_session, account, sender):
    _, smtp, factory = sender
    first = request_reset(client, "unknown@example.com")
    account.is_active = False
    sqlite_session.commit()
    second = request_reset(client)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    factory.assert_not_called()
    smtp.send_message.assert_not_called()


def test_same_smtp_sender_serves_verification_and_reset(sender):
    _, smtp, factory = sender
    mail.send_verification_email("verify@example.com", "verification-token")
    mail.send_password_reset_email("reset@example.com", "reset-token")
    assert factory.call_count == 2
    messages = [call.args[0] for call in smtp.send_message.call_args_list]
    assert messages[0]["From"] == messages[1]["From"]
    assert messages[0]["Subject"] == "Verify your DAHLIA email address"
    assert messages[1]["Subject"] == "Reset your DAHLIA password"
    assert "/verify-email#token=" in messages[0].get_content()
    assert "/reset-password#token=" in messages[1].get_content()
