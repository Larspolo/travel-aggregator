"""The price-drop message by Web Push (#514). A test double replaces webpush(): no request leaves CI."""

import json
from types import SimpleNamespace

import pytest
from alembic import command
from fastapi.testclient import TestClient
from pywebpush import WebPushException
from sqlalchemy import create_engine, inspect, text

from app import notify
from app.main import app
from app.models import PushSubscription, Setting
from tests.test_notify_ntfy import _mark
from tests.test_settings_page import _token
from tests.test_settings_page import client as login_client  # noqa: F401  (a fixture)
from tests.test_trip_booked import _alembic
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

A = "https://push.example/a"
B = "https://push.example/b"
SUB = {"endpoint": A, "keys": {"p256dh": "BPkey", "auth": "authkey"}}


@pytest.fixture
def vapid(monkeypatch):
    public, private = notify.vapid_keys()
    monkeypatch.setenv("VAPID_PUBLIC_KEY", public)
    monkeypatch.setenv("VAPID_PRIVATE_KEY", private)
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:owner@example.com")
    return public


@pytest.fixture
def pushed(monkeypatch):
    """The calls of webpush(); an endpoint in `fail` gets that HTTP status."""
    calls, fail = [], {}

    def double(subscription_info, data=None, vapid_private_key=None, vapid_claims=None, **kw):
        calls.append((subscription_info, json.loads(data), vapid_private_key, vapid_claims))
        status = fail.get(subscription_info["endpoint"])
        if status:
            raise WebPushException("push service error", response=SimpleNamespace(status_code=status, text=""))
    monkeypatch.setattr(notify, "webpush", double)
    return SimpleNamespace(calls=calls, fail=fail)


@pytest.fixture
def posted(monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "post", lambda url, text, headers: calls.append(url))
    return calls


def _setup(sessions, channel="webpush"):
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value=channel))
        s.merge(Setting(key=notify.NTFY_URL_KEY, value="https://ntfy.example/topic"))
        for endpoint in (A, B):
            s.add(PushSubscription(endpoint=endpoint, p256dh="BPkey-" + endpoint[-1], auth="auth-" + endpoint[-1]))
        s.commit()


def _drop(client, auth, trip_id, sessions):
    ingest(client, auth, trip_id, [offer("99.90")])
    _mark(sessions, trip_id)
    ingest(client, auth, trip_id, [offer("79.90")])


def _endpoints(sessions):
    with sessions() as s:
        return sorted(p.endpoint for p in s.query(PushSubscription))


def test_a_lower_price_sends_one_message_to_each_subscription(trip, sessions, vapid, pushed, posted):  # noqa: F811
    client, auth, trip_id = trip
    _setup(sessions)
    _drop(client, auth, trip_id, sessions)
    assert [c[0]["endpoint"] for c in pushed.calls] == [A, B] and posted == []
    info, data, private, claims = pushed.calls[0]
    assert info["keys"] == {"p256dh": "BPkey-a", "auth": "auth-a"}
    assert data["title"] == "Price drop: Amsterdam – Zürich" and data["url"].endswith(f"/trips/{trip_id}")
    assert "EUR 99.90" in data["body"] and "EUR 79.90" in data["body"]
    assert private and claims["sub"] == "mailto:owner@example.com"


@pytest.mark.parametrize("status", [410, 404])
def test_a_gone_subscription_is_deleted(trip, sessions, vapid, pushed, posted, status):  # noqa: F811
    client, auth, trip_id = trip
    _setup(sessions)
    pushed.fail[A] = status
    _drop(client, auth, trip_id, sessions)
    assert len(pushed.calls) == 2 and _endpoints(sessions) == [B]


def test_another_error_keeps_the_subscription(trip, sessions, vapid, pushed, posted, caplog):  # noqa: F811
    client, auth, trip_id = trip
    _setup(sessions)
    pushed.fail[A] = 500
    _drop(client, auth, trip_id, sessions)
    assert _endpoints(sessions) == [A, B] and "price drop message not sent" in caplog.text


@pytest.mark.parametrize("channel", ["ntfy", "none"])
def test_no_push_for_the_other_channels(trip, sessions, vapid, pushed, posted, channel):  # noqa: F811
    client, auth, trip_id = trip
    _setup(sessions, channel)
    _drop(client, auth, trip_id, sessions)
    assert pushed.calls == [] and len(posted) == (1 if channel == "ntfy" else 0)


def test_no_push_without_the_vapid_keys(trip, sessions, pushed, posted, monkeypatch):  # noqa: F811
    for name in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_SUBJECT"):
        monkeypatch.delenv(name, raising=False)
    client, auth, trip_id = trip
    _setup(sessions)
    _drop(client, auth, trip_id, sessions)
    assert pushed.calls == [] and posted == []


def test_subscribe_and_remove(login_client, sessions, vapid):  # noqa: F811
    page = login_client.get("/settings/messages").text
    assert f'data-key="{vapid}"' in page and "Turn on push on this device" in page and "home screen" in page
    csrf = {"X-CSRF-Token": _token(login_client, "/settings")}
    assert login_client.post("/settings/push", json=SUB, headers=csrf).json() == {"subscriptions": 1}
    renewed = {**SUB, "keys": {"p256dh": "BPnew", "auth": "new"}}
    assert login_client.post("/settings/push", json=renewed, headers=csrf).json() == {"subscriptions": 1}
    with sessions() as s:
        assert s.query(PushSubscription).one().p256dh == "BPnew"
    assert login_client.post("/settings/push/delete", json=SUB, headers=csrf).json() == {"subscriptions": 0}


@pytest.mark.parametrize("body", [{**SUB, "endpoint": "http://push.example/a"}, {"endpoint": A}])
def test_a_bad_subscription_gets_422(login_client, sessions, body):  # noqa: F811
    csrf = {"X-CSRF-Token": _token(login_client, "/settings")}
    assert login_client.post("/settings/push", json=body, headers=csrf).status_code == 422
    assert _endpoints(sessions) == []


@pytest.mark.parametrize("path", ["/settings/push", "/settings/push/delete"])
def test_the_endpoints_need_the_login_and_the_csrf_token(login_client, sessions, path):  # noqa: F811
    with sessions() as s:
        s.add(PushSubscription(endpoint=A, p256dh="k", auth="a"))
        s.commit()
    no_login = TestClient(app).post(path, json=SUB, headers={"X-CSRF-Token": "x"}, follow_redirects=False)
    assert no_login.status_code == 303 and no_login.headers["location"] == "/login"
    assert login_client.post(path, json=SUB).status_code == 403
    assert login_client.post(path, json=SUB, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert _endpoints(sessions) == [A]


def test_the_channel_webpush_needs_the_vapid_keys(login_client, monkeypatch):  # noqa: F811
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    r = login_client.post("/settings/messages", data={"notify_channel": "webpush", "ntfy_url": "",
                                             "csrf_token": _token(login_client, "/settings")}, follow_redirects=False)
    assert r.status_code == 422


def test_the_service_worker_is_at_the_root():
    r = TestClient(app).get("/sw.js")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/javascript")
    assert "notificationclick" in r.text and "showNotification" in r.text


def test_the_key_pair_has_the_sizes_of_p256():
    import base64
    public, private = notify.vapid_keys()
    decode = lambda v: base64.urlsafe_b64decode(v + "=" * (-len(v) % 4))  # noqa: E731
    assert len(decode(public)) == 65 and len(decode(private)) == 32


def test_migration_0015_up_and_down_with_data(empty_database_url):
    cfg = _alembic(empty_database_url)
    engine = create_engine(empty_database_url)
    try:
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "0014")  # empty
        assert "push_subscriptions" not in inspect(engine).get_table_names()
        command.upgrade(cfg, "head")
        with engine.begin() as c:
            c.execute(text("INSERT INTO push_subscriptions (endpoint, p256dh, auth) VALUES (:e, 'k', 'a')"), {"e": A})
            c.execute(text("INSERT INTO trips (title) VALUES ('kept')"))
        command.downgrade(cfg, "0014")  # with data
        assert "push_subscriptions" not in inspect(engine).get_table_names()
        command.upgrade(cfg, "head")
        with engine.connect() as c:
            assert c.execute(text("SELECT count(*) FROM push_subscriptions")).scalar() == 0
            assert c.execute(text("SELECT title FROM trips")).scalar() == "kept"
    finally:
        engine.dispose()
