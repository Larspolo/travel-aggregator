"""The price-drop message by e-mail (#513). A test double replaces `smtplib.SMTP`: no mail leaves CI."""

import smtplib

import pytest

from app import notify
from app.models import Setting
from tests.test_notify_ntfy import _mark
from tests.test_settings_page import _token
from tests.test_settings_page import client as login_client  # noqa: F401  (a fixture)
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

ADDRESS = "owner@example.org"


class FakeSMTP:
    sent: list = []
    fail = False

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, mail):
        if FakeSMTP.fail:
            raise smtplib.SMTPException("refused")
        FakeSMTP.sent.append(mail)


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.sent, FakeSMTP.fail = [], False
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("SMTP_FROM", "travel@example.org")
    monkeypatch.setattr(notify, "post", lambda *a: pytest.fail("no ntfy POST"))
    return FakeSMTP


def _channel(sessions, channel):
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value=channel))
        s.merge(Setting(key=notify.EMAIL_KEY, value=ADDRESS))
        s.merge(Setting(key=notify.NTFY_URL_KEY, value="https://ntfy.example/t"))
        s.commit()


def _drop(client, auth, trip_id, sessions):
    ingest(client, auth, trip_id, [offer("99.90")])
    _mark(sessions, trip_id)
    ingest(client, auth, trip_id, [offer("79.90")])


def test_a_lower_price_sends_one_email(trip, sessions, smtp):  # noqa: F811
    client, auth, trip_id = trip
    _channel(sessions, "email")
    _drop(client, auth, trip_id, sessions)
    assert len(smtp.sent) == 1
    mail = smtp.sent[0]
    body = mail.get_content()
    assert mail["To"] == ADDRESS and mail["Subject"] == "Price drop: Amsterdam – Zürich"
    assert "EUR 99.90" in body and "EUR 79.90" in body and f"/trips/{trip_id}" in body


@pytest.mark.parametrize("channel", ["none", "ntfy"])
def test_no_email_for_other_channels(trip, sessions, smtp, monkeypatch, channel):  # noqa: F811
    client, auth, trip_id = trip
    monkeypatch.setattr(notify, "post", lambda *a: None)
    _channel(sessions, channel)
    _drop(client, auth, trip_id, sessions)
    assert smtp.sent == []


def test_an_smtp_error_is_logged_and_the_ingest_works(trip, sessions, smtp, caplog):  # noqa: F811
    client, auth, trip_id = trip
    _channel(sessions, "email")
    smtp.fail = True
    _drop(client, auth, trip_id, sessions)  # asserts the status 200
    assert "price drop message not sent" in caplog.text


def _save(c, **data):
    return c.post("/settings", data={"retention": "30", "csrf_token": _token(c, "/settings"), **data},
                  follow_redirects=False)


def test_email_without_smtp_host_gets_422(login_client, monkeypatch):  # noqa: F811
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert "E-mail needs SMTP_HOST on the server" in login_client.get("/settings").text
    assert _save(login_client, notify_channel="email", notify_email=ADDRESS).status_code == 422


def test_an_address_without_at_gets_422_and_a_good_one_is_saved(login_client, monkeypatch):  # noqa: F811
    monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
    assert _save(login_client, notify_channel="email", notify_email="owner.example.org").status_code == 422
    assert _save(login_client, notify_channel="email", notify_email=ADDRESS).status_code == 303
    page = login_client.get("/settings").text
    assert f'value="{ADDRESS}"' in page and '<option value="email" selected>' in page
