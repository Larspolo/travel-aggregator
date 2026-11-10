"""The result of each sent message (#1812). Doubles replace `post`, `smtplib.SMTP` and `webpush`: no request leaves
the test."""

import smtplib
import urllib.error
from types import SimpleNamespace

from alembic import command
from pywebpush import WebPushException
from sqlalchemy import create_engine, inspect, select

from app import notify
from app.models import PushSubscription, SentMessage
from tests.test_travel_day_due import _alembic

URL = "https://ntfy.example/secret-topic"


def _msg(channel="ntfy", url=URL, title="Price drop"):
    return notify.Message(channel=channel, url=url, title=title, text="text", click="https://app/trips/1")


def _rows(sessions):
    with sessions() as s:
        return list(s.scalars(select(SentMessage).order_by(SentMessage.id)))


def test_a_sent_and_a_failed_ntfy_message(sessions, monkeypatch):
    monkeypatch.setattr(notify, "post", lambda url, text, headers: None)
    notify.deliver([_msg()], sessions)

    def fail(url, text, headers):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    monkeypatch.setattr(notify, "post", fail)
    assert notify.deliver([_msg()], sessions) == ["ntfy HTTP 404"]
    ok, bad = _rows(sessions)
    assert ok.ok and ok.reason is None and ok.channel == "ntfy" and ok.title == "Price drop"
    assert not bad.ok and bad.reason == "ntfy HTTP 404"
    for row in (ok, bad):
        assert "secret-topic" not in f"{row.title} {row.click} {row.reason}"


def test_an_smtp_error_gives_a_reason_with_no_address(sessions, monkeypatch):
    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def send_message(self, mail):
            raise smtplib.SMTPRecipientsRefused({"me@example.org": (550, b"no")})
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
    with sessions() as s:
        assert notify.deliver([_msg("email", "me@example.org")], session=s) == ["email SMTPRecipientsRefused"]
    (row,) = _rows(sessions)
    assert not row.ok and "example.org" not in row.reason


def test_a_push_error_gives_a_reason_and_gone_deletes_the_subscription(sessions, monkeypatch):
    endpoint = "https://push.example/secret-endpoint"
    with sessions() as s:
        s.add(PushSubscription(endpoint=endpoint, p256dh="k", auth="a"))
        s.commit()
    status = {"code": 500}

    def fake(*a, **k):
        raise WebPushException("push error", response=SimpleNamespace(status_code=status["code"], text=""))
    monkeypatch.setattr(notify, "webpush", fake)
    assert notify.deliver([_msg("webpush", endpoint)], sessions) == ["webpush HTTP 500"]
    status["code"] = 410
    assert notify.deliver([_msg("webpush", endpoint)], sessions) == ["webpush HTTP 410"]
    with sessions() as s:
        assert s.scalars(select(PushSubscription)).all() == []
    assert all("secret-endpoint" not in r.reason for r in _rows(sessions))


def test_the_table_keeps_the_newest_100(sessions, monkeypatch):
    monkeypatch.setattr(notify, "post", lambda url, text, headers: None)
    for i in range(101):
        notify.deliver([_msg(title=f"m{i}")], sessions)
    rows = _rows(sessions)
    assert len(rows) == 100 and rows[0].title == "m1" and rows[-1].title == "m100"


def test_the_migration_downgrades_and_upgrades(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0040")
    eng = create_engine(empty_database_url)
    assert "sent_messages" not in inspect(eng).get_table_names()
    command.upgrade(cfg, "head")
    assert "sent_messages" in inspect(eng).get_table_names()
    eng.dispose()
