"""TLS SMTP delivery and a database-backed resend cooldown.

Only the backend reads SMTP credentials. Tokens and credentials must not be
logged. Links use a fragment so the verification token is not in access logs.
"""

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
import smtplib
import ssl
from urllib.parse import quote

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_email_verification_token
from app.models.user import AppUser


class EmailDeliveryError(Exception):
    """The server could not submit the verification message to SMTP."""


class EmailCooldownError(Exception):
    """A message was requested too recently for this account."""


def send_verification_email(recipient: str, token: str) -> None:
    settings = get_settings()
    if settings.EMAIL_DELIVERY_MODE != "smtp":
        raise EmailDeliveryError("Verification email delivery is not configured.")
    link = (settings.PUBLIC_API_URL.rstrip("/")
            + "/api/v1/auth/verify-email#token=" + quote(token, safe=""))
    message = EmailMessage()
    message["Subject"] = "Verify your DAHLIA email address"
    message["From"] = formataddr(("DAHLIA", str(settings.SMTP_FROM_EMAIL)))
    message["To"] = recipient
    message.set_content(
        "Confirm your email address to upload DAHLIA experiments.\n\n"
        f"Open this link and click Confirm email:\n{link}\n\n"
        "The link expires in 24 hours. After confirmation, return to the app "
        "and click Check verification status in Profile.\n\n"
        "If you did not request this message, you can ignore it.\n"
    )
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT,
                          timeout=settings.SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD.get_secret_value())
            refused = smtp.send_message(message)
            if refused:
                raise EmailDeliveryError("SMTP refused the recipient.")
    except (smtplib.SMTPException, OSError) as exc:
        # Do not expose provider responses, message bodies or credentials.
        raise EmailDeliveryError("SMTP could not deliver the verification message.") from exc


def request_verification_email(db: Session, user: AppUser) -> None:
    if user.is_email_verified:
        return
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=get_settings().EMAIL_RESEND_COOLDOWN_SECONDS)
    # Conditional UPDATE prevents concurrent requests and survives restarts.
    result = db.execute(
        update(AppUser).where(
            AppUser.user_id == user.user_id,
            AppUser.is_active == True,  # noqa: E712 - MSSQL BIT uses = 1
            AppUser.is_email_verified == False,  # noqa: E712
            or_(AppUser.email_verification_sent_at.is_(None),
                AppUser.email_verification_sent_at <= cutoff),
        ).values(email_verification_sent_at=now)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise EmailCooldownError()
    db.commit()
    # Keep the cooldown after failures too, to avoid SMTP flooding.
    token = create_email_verification_token(user.user_id, user.email)
    send_verification_email(user.email, token)
