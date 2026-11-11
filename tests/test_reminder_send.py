"""The daily loop of the backup service sends the "Search again" reminders (#1119). Doubles replace the sends."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app import backup, notify, reminder
from app.models import Setting, Trip
from tests.test_trip_page import trip  # noqa: F401  (a fixture)

NTFY = "https://ntfy.example/topic"
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
DAY = timedelta(hours=24)


@pytest.fixture
def setup(monkeypatch, sessions, tmp_path):
    with sessions() as s:
        for key, value in [(notify.CHANNEL_KEY, "ntfy"), (notify.NTFY_URL_KEY, NTFY),
                           (notify.REMINDER_DAYS_KEY, "3"), (reminder.BASE_URL_KEY, "https://travel.example/")]:
            s.merge(Setting(key=key, value=value))
        trip = Trip(title="Berlin weekend", origin_text="Amsterdam", destination_text="Berlin", status="planning",
                    date_from=NOW.date() + timedelta(days=5), target_price=Decimal("80"))
        s.add(trip)
        s.commit()
        trip_id = trip.id
    calls = []
    monkeypatch.setattr(notify, "post", lambda url, text, headers: calls.append((headers["Title"], text, headers["Click"])))
    monkeypatch.setattr(notify, "send_email", lambda m: calls.append(m))
    monkeypatch.setattr(notify, "push", lambda m: calls.append(m))
    dumps = []
    monkeypatch.setattr(backup, "dump", lambda u, d, kind: dumps.append(kind))
    monkeypatch.setattr(backup, "_check_step", lambda u, path, now: None)
    return calls, dumps, trip_id


def _reminded(sessions, trip_id):
    with sessions() as s:
        return s.get(Trip, trip_id).reminded_at


def test_one_step_sends_one_message_and_a_second_step_none(migrated_url, sessions, setup, tmp_path):
    calls, dumps, trip_id = setup
    backup.daily_step(migrated_url, tmp_path, DAY, now=NOW)
    assert dumps == ["daily"] and len(calls) == 1
    title, text, click = calls[0]
    assert title == "Search again: Berlin weekend"
    assert click == f"https://travel.example/trips/{trip_id}" and click in text
    assert "https://" in text.replace(click, "")  # the search links of the trip
    assert _reminded(sessions, trip_id) == NOW
    backup.daily_step(migrated_url, tmp_path, DAY, now=NOW + timedelta(hours=2))
    assert len(calls) == 1


def test_a_failure_is_logged_and_the_dump_still_runs(migrated_url, setup, tmp_path, monkeypatch, caplog):
    calls, dumps, _ = setup

    def boom(*a):
        raise RuntimeError("no reminders")
    monkeypatch.setattr(reminder, "send_reminders", boom)
    assert backup.daily_step(migrated_url, tmp_path, DAY, now=NOW) == DAY.total_seconds()
    assert dumps == ["daily"] and calls == [] and "reminders not sent: no reminders" in caplog.text


def test_the_channel_none_sends_nothing_and_marks_nothing(migrated_url, sessions, setup, tmp_path):
    calls, _, trip_id = setup
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value="none"))
        s.commit()
    backup.daily_step(migrated_url, tmp_path, DAY, now=NOW)
    assert calls == [] and _reminded(sessions, trip_id) is None


def test_an_ingest_stores_the_base_url_of_the_reminders(trip, sessions):  # noqa: F811
    from tests.test_trip_page import ingest, offer
    client, auth, tid = trip
    ingest(client, auth, tid, [offer("89.90", "ICE 1")])
    with sessions() as s:
        assert notify.setting(s, reminder.BASE_URL_KEY) == "http://testserver/"
