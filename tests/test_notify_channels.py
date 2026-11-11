"""The price-drop message of each channel of `notify_channel` (#523): the same cases for ntfy, e-mail, Web Push and
none. Test doubles replace every sender: no message leaves CI."""

import copy
import smtplib
import urllib.error
from types import SimpleNamespace

import pytest
from pywebpush import WebPushException

from app import notify
from app.models import PushSubscription, Setting
from tests.test_notify_ntfy import _mark
from tests.test_trip_page import BODY, offer, trip  # noqa: F401  (trip is a fixture)

CHANNELS = ("none", "ntfy", "email", "webpush")
SENDING = ("ntfy", "email", "webpush")
URL = "https://ntfy.example/topic"
ADDRESS = "owner@example.org"
ENDPOINT = "https://push.example/a"


@pytest.fixture
def doubles(monkeypatch):
    """The calls of each sender, by channel; an entry of `fail` makes that sender raise."""
    rec = SimpleNamespace(calls=[], fail={})

    class FakeSMTP:
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
            rec.calls.append("email")
            if "email" in rec.fail:
                raise rec.fail["email"]

    def ntfy_post(url, text, headers):
        rec.calls.append("ntfy")
        if "ntfy" in rec.fail:
            raise rec.fail["ntfy"]

    def web_push(subscription_info, data=None, **kw):
        rec.calls.append("webpush")
        if "webpush" in rec.fail:
            raise rec.fail["webpush"]

    monkeypatch.setattr(notify, "post", ntfy_post)
    monkeypatch.setattr(notify, "webpush", web_push)
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("SMTP_FROM", "travel@example.org")
    return rec


@pytest.fixture
def vapid(monkeypatch):
    public, private = notify.vapid_keys()
    monkeypatch.setenv("VAPID_PUBLIC_KEY", public)
    monkeypatch.setenv("VAPID_PRIVATE_KEY", private)
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:owner@example.com")


def _setup(sessions, channel):
    """All settings and one push subscription; the channel can change later with `_set_channel`."""
    with sessions() as s:
        s.merge(Setting(key=notify.NTFY_URL_KEY, value=URL))
        s.merge(Setting(key=notify.EMAIL_KEY, value=ADDRESS))
        s.add(PushSubscription(endpoint=ENDPOINT, p256dh="BPkey-a", auth="auth-a"))
        s.commit()
    _set_channel(sessions, channel)


def _set_channel(sessions, channel):
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value=channel))
        s.commit()


def _post(client, auth, trip_id, price):
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, offers=[offer(price)])
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200
    return r.json()


@pytest.mark.parametrize("channel", SENDING)
def test_a_lower_price_sends_one_message_on_its_channel(trip, sessions, vapid, doubles, channel):  # noqa: F811
    client, auth, trip_id = trip
    _setup(sessions, channel)
    _post(client, auth, trip_id, "99.90")
    _mark(sessions, trip_id)
    _post(client, auth, trip_id, "79.90")
    assert doubles.calls == [channel]


@pytest.mark.parametrize("channel,case", [(c, case) for c in CHANNELS for case in ("same", "unpinned")]
                         + [("none", "lower")])
def test_no_message_for_the_same_price_an_unpinned_fare_or_no_channel(trip, sessions, vapid, doubles,  # noqa: F811
                                                                     channel, case):
    client, auth, trip_id = trip
    _setup(sessions, channel)
    _post(client, auth, trip_id, "99.90")
    _mark(sessions, trip_id, pinned=case != "unpinned")
    _post(client, auth, trip_id, "79.90" if case == "lower" else "99.90")
    assert doubles.calls == []


@pytest.mark.parametrize("channel,error", [
    ("ntfy", TimeoutError("timed out")),
    ("ntfy", urllib.error.HTTPError(URL, 500, "error", None, None)),
    ("email", smtplib.SMTPException("refused")),
    ("webpush", WebPushException("push service error", response=SimpleNamespace(status_code=500, text=""))),
], ids=["ntfy-timeout", "ntfy-http-500", "email-smtp", "webpush-500"])
def test_a_send_error_is_logged_and_the_response_is_the_same(trip, sessions, vapid, doubles, caplog,  # noqa: F811
                                                             channel, error):
    client, auth, trip_id = trip
    _setup(sessions, "none")
    _post(client, auth, trip_id, "99.90")
    _mark(sessions, trip_id)
    without = _post(client, auth, trip_id, "79.90")  # no send: the channel is none
    _set_channel(sessions, channel)
    doubles.fail[channel] = error
    with_error = _post(client, auth, trip_id, "59.90")
    assert {**with_error, "best": None} == {**without, "best": None}  # the best offer changes with the price (#880)
    assert doubles.calls == [channel]
    assert caplog.text.count("price drop message not sent") == 1
