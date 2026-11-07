"""A ntfy message when a capture lowers the price of a pinned fare (#512). A test double replaces the POST."""

import urllib.error

import pytest

from app import notify
from app.models import Itinerary, Setting
from tests.test_settings_page import _token
from tests.test_settings_page import client as login_client  # noqa: F401  (a fixture)
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

URL = "https://ntfy.example/topic"


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "post", lambda url, text, headers: calls.append((url, text, headers)))
    return calls


def _channel(sessions, channel="ntfy"):
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value=channel))
        s.merge(Setting(key=notify.NTFY_URL_KEY, value=URL))
        s.commit()


def _mark(sessions, trip_id, pinned=True, hidden=False):
    with sessions() as s:
        for it in s.query(Itinerary).filter_by(trip_id=trip_id):
            it.pinned, it.hidden = pinned, hidden
        s.commit()


def test_a_lower_price_of_a_pinned_fare_sends_one_message(trip, sessions, sent):  # noqa: F811
    client, auth, trip_id = trip
    _channel(sessions)
    ingest(client, auth, trip_id, [offer("99.90")])
    _mark(sessions, trip_id)
    ingest(client, auth, trip_id, [offer("79.90")])
    assert len(sent) == 1
    url, text, headers = sent[0]
    assert url == URL and "Sparpreis" in text and "EUR 99.90" in text and "EUR 79.90" in text
    assert headers["Title"].encode("latin-1").decode() == "Price drop: Amsterdam – Zürich"
    assert headers["Click"].endswith(f"/trips/{trip_id}")


def test_two_lower_fares_give_one_message_with_two_lines(trip, sessions, sent):  # noqa: F811
    client, auth, trip_id = trip
    _channel(sessions)
    ingest(client, auth, trip_id, [offer("99.90", "ICE 1"), offer("89.90", "ICE 2")])
    _mark(sessions, trip_id)
    ingest(client, auth, trip_id, [offer("79.90", "ICE 1"), offer("69.90", "ICE 2")])
    assert len(sent) == 1 and len(sent[0][1].splitlines()) == 2


@pytest.mark.parametrize("case", ["same", "higher", "unpinned", "hidden", "currency", "none"])
def test_no_message(trip, sessions, sent, case):  # noqa: F811
    client, auth, trip_id = trip
    _channel(sessions, "none" if case == "none" else "ntfy")
    ingest(client, auth, trip_id, [offer("99.90")])
    _mark(sessions, trip_id, pinned=case != "unpinned", hidden=case == "hidden")
    second = offer({"same": "99.90", "higher": "109.90"}.get(case, "79.90"))
    if case == "currency":
        second["price_currency"] = "CHF"
    ingest(client, auth, trip_id, [second])
    assert sent == []


@pytest.mark.parametrize("error", [TimeoutError("timed out"),
                                   urllib.error.HTTPError(URL, 500, "error", None, None)])
def test_a_failed_post_is_logged_and_the_response_is_the_same(trip, sessions, monkeypatch, caplog, error):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("99.90")])
    _mark(sessions, trip_id)

    def fail(url, text, headers):
        raise error
    monkeypatch.setattr(notify, "post", fail)
    body = {"trip_id": trip_id, "offers": [offer("79.90")]}
    from tests.test_trip_page import BODY
    full = {**BODY, **body}
    without = client.post("/api/ingest", json=full, headers=auth).json()
    _channel(sessions)
    full["offers"] = [offer("59.90")]
    with_channel = client.post("/api/ingest", json=full, headers=auth)
    assert with_channel.status_code == 200 and with_channel.json() == without
    assert "price drop message not sent" in caplog.text


def test_settings_save_the_channel_and_the_url(login_client):  # noqa: F811
    r = login_client.post("/settings", data={"retention": "30", "notify_channel": "ntfy", "ntfy_url": URL,
                                             "csrf_token": _token(login_client, "/settings")}, follow_redirects=False)
    assert r.status_code == 303
    page = login_client.get("/settings").text
    assert f'value="{URL}"' in page and '<option value="ntfy" selected>' in page


@pytest.mark.parametrize("url", ["http://ntfy.sh/topic", "ntfy.sh/topic"])
def test_a_url_without_https_gets_422(login_client, url):  # noqa: F811
    r = login_client.post("/settings", data={"retention": "30", "notify_channel": "ntfy", "ntfy_url": url,
                                             "csrf_token": _token(login_client, "/settings")}, follow_redirects=False)
    assert r.status_code == 422
