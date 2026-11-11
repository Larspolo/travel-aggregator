"""The JSON export of the settings (#1206)."""

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import require_login
from app.main import app
from app.models import AccessTime, ApiToken, CurrencyRate, PushSubscription, ScoreProfile, Setting, SourceFee

NOW = datetime(2026, 11, 8, tzinfo=timezone.utc)
SECRETS = {
    "notify_channel": "secret-channel-x1", "ntfy_url": "https://ntfy.example/secret-topic-x2",
    "notify_email": "secret-x3@example.org", "calendar_feed_hash": "secret-feed-x4",
    "backup_alert_at": "secret-state-x5", "base_url": "https://secret-x6.example",
    "source_health:bahn": "secret-state-x7",
}


@pytest.fixture
def filled(sessions):
    with sessions() as s:
        s.add(ScoreProfile(name="Cheap", is_default=True, config_json={"price_weight": 1.0}))
        s.add(AccessTime(place_text="Home", kind="access", minutes=15, cost=Decimal("2.50")))
        s.add(CurrencyRate(code="CHF", eur_per_unit=Decimal("1.064512"), updated_at=NOW))
        s.add(SourceFee(source="bahn", amount=Decimal("1.99"), updated_at=NOW))
        s.add(Setting(key="capture_retention_days", value="30"))
        s.add(Setting(key="reminder_days", value="7"))
        for key, value in SECRETS.items():
            s.add(Setting(key=key, value=value))
        s.add(ApiToken(name="tm", token_hash="secret-token-hash-x8"))
        s.add(PushSubscription(endpoint="https://push.example/secret-x9", p256dh="secret-p-x10", auth="secret-a-x11"))
        s.commit()


@pytest.fixture
def client():
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.pop(require_login, None)


def test_the_export_has_all_rows(client, filled):
    r = client.get("/settings/export.json")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    assert r.headers["content-disposition"].startswith('attachment; filename="travel-aggregator-settings-')
    data = r.json()
    assert data["format"] == "travel-aggregator-settings" and data["version"] == 1 and data["exported_at"]
    assert data["profiles"] == [{"name": "Cheap", "is_default": True, "config": {"price_weight": 1.0}}]
    assert data["places"] == [{"place": "Home", "kind": "access", "minutes": 15, "cost": "2.50"}]
    assert data["rates"] == [{"code": "CHF", "eur_per_unit": "1.064512"}]
    assert data["fees"] == [{"source": "bahn", "amount": "1.99"}]
    assert data["settings"] == {"capture_retention_days": "30", "reminder_days": "7"}


def test_the_export_has_no_secret(client, filled):
    text = client.get("/settings/export.json").text
    assert "secret" not in text
    for key in SECRETS:
        assert key not in json.loads(text)["settings"]


def test_no_login_goes_to_the_login_page():
    r = TestClient(app).get("/settings/export.json", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=%2F")  # the target of #2103


def test_the_settings_page_has_the_link(client, sessions):
    r = client.get("/settings")
    assert r.status_code == 200 and 'href="/settings/export.json"' in r.text and "Export the settings" in r.text
