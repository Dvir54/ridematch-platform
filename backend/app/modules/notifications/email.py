"""Email delivery behind one function, with a swappable backend (`EMAIL_BACKEND`).

- `console` (dev/test default): logs the message
- `memory`: appends to `outbox`, which tests read
- `smtp`: sends through `SMTP_*`, with a timeout

Services queue mail on the session and `dispatch` it once the transaction has committed, so an
email never goes out for a rolled-back write and a request never waits on the mail server.
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

SMTP_TIMEOUT_SECONDS = 10
#: Port 465 is implicit TLS; every other port speaks plain SMTP and upgrades with STARTTLS.
SMTP_SSL_PORT = 465

#: SMTP sends in flight, held so they aren't garbage-collected mid-send; `drain` awaits them.
_tasks: set[asyncio.Task] = set()


def _send_smtp(settings: Settings, message: EmailMessage) -> None:
    mime = MimeMessage()
    mime["From"] = settings.email_from
    mime["To"] = message.to
    mime["Subject"] = message.subject
    mime.set_content(message.body)
    implicit_tls = settings.smtp_port == SMTP_SSL_PORT
    smtp_class = smtplib.SMTP_SSL if implicit_tls else smtplib.SMTP
    with smtp_class(settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
        if not implicit_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(mime)


def _deliver_locally(settings: Settings, message: EmailMessage) -> None:
    """The console and memory backends: no I/O."""
    if settings.email_backend == "memory":
        outbox.append(message)
    else:
        logger.info(
            "[email:console] to=%s subject=%s\n%s", message.to, message.subject, message.body
        )


async def send_email(
    settings: Settings, to: str, subject: str, body: str, *, user_id: int | None = None
) -> EmailMessage:
    """Never raises: a failed send is logged by user id, never by address."""
    message = EmailMessage(to=to, subject=subject, body=body)
    try:
        if settings.email_backend == "smtp":
            await asyncio.to_thread(_send_smtp, settings, message)
        else:
            _deliver_locally(settings, message)
    except Exception:
        logger.exception("Sending email to user %s failed", user_id)
    return message


def dispatch(settings: Settings, to: str, subject: str, body: str, *, user_id: int) -> None:
    """Send mail whose transaction has committed, without waiting for the mail server."""
    if settings.email_backend != "smtp":
        _deliver_locally(settings, EmailMessage(to=to, subject=subject, body=body))
        return
    task = asyncio.create_task(send_email(settings, to, subject, body, user_id=user_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def drain(wait_seconds: float = 10.0) -> None:
    """Wait up to `wait_seconds` for the SMTP sends in flight. Called at shutdown, and by tests."""
    if _tasks:
        await asyncio.wait(set(_tasks), timeout=wait_seconds)
