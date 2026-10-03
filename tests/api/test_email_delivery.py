"""Email leaves only after the transaction commits, never holds up the caller, and has a
timeout (plan §8; CONTRACT.md §7 says which events send one)."""

from __future__ import annotations

import logging
import time
from typing import ClassVar

import pytest


async def _notify(session, settings, user_id: int, to: str) -> None:
    from app.modules.notifications.service import EmailContent, notify

    await notify(
        session,
        settings,
        user_id=user_id,
        type="welcome",
        title="Welcome",
        message="Hi",
        email=EmailContent(to=to, subject="Hi", body="Body"),
        push=False,
    )


async def test_nothing_is_sent_when_the_transaction_rolls_back(backend_app, user, outbox) -> None:
    outbox.clear()
    async with backend_app.state.sessionmaker() as session:
        await _notify(session, backend_app.state.settings, user.id, user.email)
        await session.rollback()
    assert outbox == []


async def test_the_email_is_sent_after_commit(backend_app, user, outbox) -> None:
    from app.modules.notifications.service import commit_and_push

    outbox.clear()
    async with backend_app.state.sessionmaker() as session:
        await _notify(session, backend_app.state.settings, user.id, user.email)
        assert outbox == [], "nothing leaves before the commit"
        await commit_and_push(session)
    assert [message.to for message in outbox] == [user.email]


async def test_a_slow_mail_server_does_not_hold_the_caller(backend_app, monkeypatch) -> None:
    from app.modules.notifications import email

    sent: list[str] = []

    def slow_send(settings, message) -> None:
        time.sleep(0.5)
        sent.append(message.to)

    monkeypatch.setattr(email, "_send_smtp", slow_send)
    smtp = backend_app.state.settings.model_copy(update={"email_backend": "smtp"})

    started = time.perf_counter()
    email.dispatch(smtp, "a@ridematch.test", "s", "b", user_id=1)
    assert time.perf_counter() - started < 0.1
    assert sent == []

    await email.drain(wait_seconds=5)
    assert sent == ["a@ridematch.test"]


async def test_a_failed_send_logs_the_user_id_not_the_address(
    backend_app, monkeypatch, caplog
) -> None:
    from app.modules.notifications import email

    def broken(settings, message) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr(email, "_send_smtp", broken)
    smtp = backend_app.state.settings.model_copy(update={"email_backend": "smtp"})
    with caplog.at_level(logging.ERROR):
        email.dispatch(smtp, "secret-person@ridematch.test", "s", "b", user_id=42)
        await email.drain(wait_seconds=5)
    assert "user 42" in caplog.text
    assert "secret-person" not in caplog.text


class _FakeSmtp:
    instances: ClassVar[list[_FakeSmtp]] = []

    def __init__(self, host, port, timeout=None) -> None:
        self.timeout = timeout
        self.started_tls = False
        _FakeSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, user, password) -> None:
        pass

    def send_message(self, mime) -> None:
        pass


class _FakeSmtpSsl(_FakeSmtp):
    pass


@pytest.mark.parametrize(("port", "implicit_tls"), [(587, False), (465, True)])
def test_smtp_has_a_timeout_and_uses_implicit_tls_on_465(
    backend_app, monkeypatch, port: int, implicit_tls: bool
) -> None:
    from app.modules.notifications import email

    _FakeSmtp.instances.clear()
    monkeypatch.setattr(email.smtplib, "SMTP", _FakeSmtp)
    monkeypatch.setattr(email.smtplib, "SMTP_SSL", _FakeSmtpSsl)
    settings = backend_app.state.settings.model_copy(
        update={"email_backend": "smtp", "smtp_host": "smtp.example.com", "smtp_port": port}
    )
    email._send_smtp(settings, email.EmailMessage(to="a@b.c", subject="s", body="b"))

    [smtp] = _FakeSmtp.instances
    assert smtp.timeout == 10
    assert isinstance(smtp, _FakeSmtpSsl) is implicit_tls
    assert smtp.started_tls is not implicit_tls
