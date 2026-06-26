"""Send transactional email (invite, password reset)."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from src.config import get_settings

logger = logging.getLogger(__name__)


def send_email(*, to: str, subject: str, body_text: str, body_html: str | None = None) -> None:
    settings = get_settings()
    if not settings.EMAIL_ENABLED or not settings.SMTP_HOST:
        logger.info(
            "Email (dev mode — not sent)\n  To: %s\n  Subject: %s\n  Body:\n%s",
            to,
            subject,
            body_text,
        )
        print(f"\n--- EMAIL to {to} ---\nSubject: {subject}\n{body_text}\n---\n")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as smtp:
        if settings.SMTP_USE_TLS:
            smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)


def send_password_reset_email(*, to: str, reset_url: str, purpose: str = "reset") -> None:
    if purpose == "invite":
        subject = "You're invited to Cloud Compliance"
        intro = "An administrator created an account for you. Set your password using the link below:"
    else:
        subject = "Reset your Cloud Compliance password"
        intro = "We received a request to reset your password. Use the link below:"

    body = (
        f"{intro}\n\n{reset_url}\n\n"
        f"This link expires in 24 hours. If you did not request this, you can ignore this email."
    )
    html = (
        f"<p>{intro}</p>"
        f'<p><a href="{reset_url}">{reset_url}</a></p>'
        f"<p>This link expires in 24 hours.</p>"
    )
    send_email(to=to, subject=subject, body_text=body, body_html=html)
