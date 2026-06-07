"""
Email service for applicant communication.

Sends emails via SMTP using aiosmtplib for async operations.
Configuration is sourced from app.config.settings (smtp_host, smtp_port,
smtp_user, smtp_password, smtp_from_email).
"""

import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)


async def send_email(to_email: str, subject: str, body: str) -> None:
    """
    Send an email to the specified recipient via SMTP.

    Args:
        to_email: Recipient email address.
        subject: Email subject line.
        body: Plain-text email body.

    Raises:
        RuntimeError: If the email could not be sent.
    """
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )
        logger.info(f"Email sent successfully to {to_email}")
    except aiosmtplib.SMTPException as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        raise RuntimeError(f"Failed to send email: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error sending email to {to_email}: {e}")
        raise RuntimeError(f"Failed to send email: {e}") from e
