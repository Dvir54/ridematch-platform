"""Email delivery behind one function, with a swappable backend (`EMAIL_BACKEND`).

- `console` (dev/test default): logs the message
- `memory`: appends to `outbox`, which tests read
- `smtp`: sends through `SMTP_*`
"""

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: str
    subject: str
    body: str


#: In-memory outbox for `EMAIL_BACKEND=memory`. Tests read and clear this list.
outbox: list[EmailMessage] = []


def _send_smtp(settings: Settings, message: EmailMessage) -> None:
    mime = MimeMessage()
    mime["From"] = settings.email_from
    mime["To"] = message.to
    mime["Subject"] = message.subject
    mime.set_content(message.body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(mime)


async def send_email(settings: Settings, to: str, subject: str, body: str) -> EmailMessage:
    """Never raises: a failed send is logged, because it must not fail the request."""
    message = EmailMessage(to=to, subject=subject, body=body)
    try:
        if settings.email_backend == "memory":
            outbox.append(message)
        elif settings.email_backend == "smtp":
            await asyncio.to_thread(_send_smtp, settings, message)
        else:
            logger.info("[email:console] to=%s subject=%s\n%s", to, subject, body)
    except Exception:
        logger.exception("Sending email to %s failed", to)
    return message
