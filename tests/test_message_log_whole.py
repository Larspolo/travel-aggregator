"""The whole message log (#1814): a capture brings a fare to the target price, the send fails, the messages page shows
the failure; a test message then works and shows on top. A test double replaces the POST: no request leaves the test."""

import urllib.error
from decimal import Decimal

import pytest

from app import notify
from app.models import SentMessage, Setting, Trip
from tests.test_settings_page import _token  # noqa: F401
from tests.test_settings_page import client as login_client  # noqa: F401  (a fixture)
from tests.test_trip_page import BODY, ingest, offer, trip  # noqa: F401  (trip is a fixture)

URL = "https://ntfy.example/private-topic-x7"
TITLE = "Test message from travel-aggregator"


@pytest.fixture
def post(monkeypatch):
    """The ntfy sender: starts as a failing double (HTTP 404); a test may replace it with a working one."""
    calls = []

    def fail(url, text, headers):
        calls.append((url, text, headers))
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(notify, "post", fail)
    return calls


def _setup(sessions, trip_id):
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value="ntfy"))
        s.merge(Setting(key=notify.NTFY_URL_KEY, value=URL))
        s.get(Trip, trip_id).target_price = Decimal("80.00")
        s.commit()


def test_a_failed_target_message_shows_on_the_messages_page(trip, sessions, post, login_client):  # noqa: F811
    client, auth, trip_id = trip
    _setup(sessions, trip_id)
    ingest(client, auth, trip_id, [offer("78.00")])
    assert len(post) == 1
    page = login_client.get("/settings/messages").text
    assert "Target price: Amsterdam – Zürich" in page
    assert "failed: ntfy HTTP 404" in page


def test_a_test_message_with_a_working_channel_shows_on_top(trip, sessions, post, monkeypatch, login_client):  # noqa: F811
    client, auth, trip_id = trip
    _setup(sessions, trip_id)
    ingest(client, auth, trip_id, [offer("78.00")])
    sent = []
    monkeypatch.setattr(notify, "post", lambda url, text, headers: sent.append((url, text, headers)))
    r = login_client.post("/settings/messages/test", data={"csrf_token": _token(login_client, "/settings/messages")})
    assert r.status_code == 200 and "Test message sent by ntfy" in r.text
    assert len(sent) == 1 and sent[0][0] == URL
    page = login_client.get("/settings/messages").text
    assert page.index(TITLE) < page.index("Target price: Amsterdam – Zürich")
    assert page.index(TITLE) < page.index("failed: ntfy HTTP 404")
    assert ">sent<" in page[page.index(TITLE):page.index("</tr>", page.index(TITLE))]


def test_the_topic_url_is_in_neither_the_page_nor_the_rows(trip, sessions, post, monkeypatch, login_client):  # noqa: F811
    client, auth, trip_id = trip
    _setup(sessions, trip_id)
    ingest(client, auth, trip_id, [offer("78.00")])
    monkeypatch.setattr(notify, "post", lambda url, text, headers: None)
    login_client.post("/settings/messages/test", data={"csrf_token": _token(login_client, "/settings/messages")})
    page = login_client.get("/settings/messages").text
    log = page[page.index("Last messages"):page.index("Web Push")]  # the log only: the form shows the owner's own setting
    assert "Target price" in log and URL not in log and "private-topic-x7" not in log
    with sessions() as s:
        rows = s.query(SentMessage).all()
        assert len(rows) == 2
        for row in rows:
            for value in (row.title, row.click, row.channel, row.reason or ""):
                assert "private-topic-x7" not in value and URL not in value
