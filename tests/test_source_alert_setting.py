"""The checkbox of the messages of failing sources on the messages settings page (#1174)."""

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from app import notify
from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Setting, Trip
from app.sourcehealth import source_alert_messages
from tests.test_settings_page import PASSWORD, _token

T0 = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _checked(c):
    html = c.get("/settings/messages").text
    box = re.search(r'<input type="checkbox" name="source_alert"[^>]*>', html).group(0)
    return " checked" in box


def _save(c, checkbox):
    """A form post: the hidden 0 is always sent; the checkbox 1 only when it is checked (as the browser does)."""
    data = [("notify_channel", "none"), ("ntfy_url", ""), ("notify_email", ""),
            ("reminder_days", "0"), ("reminder_before_days", "14"), ("source_alert", "0"),
            ("csrf_token", _token(c, "/settings/messages"))]
    if checkbox:
        data.insert(-1, ("source_alert", "1"))
    return _post(c, data)


def _post(c, data):
    """The form body as a string: a list of pairs with a repeated name needs the body, not the data argument."""
    return c.post("/settings/messages", content=urlencode(data),
                  headers={"Content-Type": "application/x-www-form-urlencoded"}, follow_redirects=False)


def _stored(sessions):
    with sessions() as s:
        row = s.get(Setting, notify.SOURCE_ALERT_KEY)
        return row.value if row is not None else None


def test_checkbox_is_checked_when_no_value_is_stored(client):
    assert _checked(client)


def test_save_unchecked_stores_zero_and_shows_it_unchecked(sessions, client):
    assert _save(client, checkbox=False).status_code == 303
    assert _stored(sessions) == "0"
    assert not _checked(client)


def test_save_checked_stores_one_and_shows_it_checked(sessions, client):
    _save(client, checkbox=False)
    assert _save(client, checkbox=True).status_code == 303
    assert _stored(sessions) == "1"
    assert _checked(client)


def test_a_form_without_the_field_keeps_the_value(sessions, client):
    assert _save(client, checkbox=False).status_code == 303
    data = {"notify_channel": "none", "ntfy_url": "", "notify_email": "",
            "csrf_token": _token(client, "/settings/messages")}
    assert _post(client, data).status_code == 303
    assert _stored(sessions) == "0"


def test_value_zero_gives_no_message_for_two_failed_captures(sessions):
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value="ntfy"))
        s.merge(Setting(key=notify.NTFY_URL_KEY, value="https://ntfy.example/topic"))
        s.merge(Setting(key=notify.SOURCE_ALERT_KEY, value="0"))
        trip = Trip(title="Reise")
        s.add(trip)
        s.flush()
        for h, ok in [(0, True), (1, False), (2, False)]:
            s.add(Capture(trip_id=trip.id, source="bahn.de", parser_version="1.1.0",
                          captured_at=T0 + timedelta(hours=h), offer_count=3 if ok else 0, rejected_count=0,
                          unreadable=None if ok else "no JSON"))
        s.commit()
    with sessions() as s:
        assert source_alert_messages(s, "https://trips.example") == []
        s.commit()
    with sessions() as s:
        assert s.query(Setting).filter(Setting.key.startswith("source_alert:")).count() == 0
