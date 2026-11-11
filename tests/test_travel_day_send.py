"""The travel-day messages are sent once by the active channel, from the daily loop (#1649). Doubles replace the sends."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app import backup, notify, reminder, travel_day
from app.models import Itinerary, Leg, Setting, Trip

NTFY = "https://ntfy.example/topic"
BASE = "https://travel.example/"
NOW = datetime(2026, 11, 30, 7, 15, tzinfo=UTC)  # the example of trip:travel-day: 24 hours before the departure


@pytest.fixture
def setup(monkeypatch, sessions):
    with sessions() as s:
        for key, value in [(notify.CHANNEL_KEY, "ntfy"), (notify.NTFY_URL_KEY, NTFY),
                           (travel_day.TRAVEL_DAY_HOURS_KEY, "24"), (reminder.BASE_URL_KEY, BASE)]:
            s.merge(Setting(key=key, value=value))
        trip = Trip(title="Zürich", origin_text="Amsterdam", destination_text="Zürich", status="planning")
        trip.itineraries = [Itinerary(
            fingerprint="ice", depart_at=datetime(2026, 12, 1, 7, 15, tzinfo=UTC),
            arrive_at=datetime(2026, 12, 1, 15, 2, tzinfo=UTC), duration_min=467, booked=True,
            booked_price=Decimal("89.90"), booked_currency="EUR", legs=[
                Leg(seq=0, mode="train", carrier="DB", service_no="ICE 105", from_name="Amsterdam Centraal",
                    to_name="Köln", depart_at=datetime(2026, 12, 1, 7, 15, tzinfo=UTC), depart_offset_min=60,
                    arrive_at=datetime(2026, 12, 1, 9, 26, tzinfo=UTC), arrive_offset_min=60),
                Leg(seq=1, mode="train", carrier="SBB", service_no="IC 2", from_name="Köln", to_name="Zürich HB",
                    depart_at=datetime(2026, 12, 1, 11, 0, tzinfo=UTC), depart_offset_min=60,
                    arrive_at=datetime(2026, 12, 1, 15, 2, tzinfo=UTC), arrive_offset_min=60),
            ])]
        s.add(trip)
        s.commit()
        itinerary_id = trip.itineraries[0].id
    calls = []
    # ntfy reads the raw bytes of the header as UTF-8 (notify.deliver): the double decodes the same way
    monkeypatch.setattr(notify, "post", lambda url, text, headers: calls.append(
        (headers["Title"].encode("latin-1").decode(), text, headers["Click"])))
    return calls, itinerary_id


def _marked(sessions, itinerary_id):
    with sessions() as s:
        return s.get(Itinerary, itinerary_id).travel_day_sent_at


def test_the_due_journey_gets_one_message_and_a_second_call_none(sessions, setup):
    calls, itinerary_id = setup
    with sessions() as s:
        assert travel_day.send_travel_days(s, NOW, BASE) == 1
    assert len(calls) == 1
    title, text, click = calls[0]
    assert title == "Tomorrow 08:15 Amsterdam Centraal → 16:02 Zürich HB"
    assert "DB ICE 105: Amsterdam Centraal → Köln 08:15 → 10:26" in text
    assert "change in Köln" in text
    assert "Paid 89.90 EUR" in text
    assert click == f"{BASE}upcoming?only={itinerary_id}" and click in text
    assert _marked(sessions, itinerary_id) == NOW
    with sessions() as s:
        assert travel_day.send_travel_days(s, NOW + timedelta(hours=2), BASE) == 0
    assert len(calls) == 1


def test_the_channel_none_sends_nothing_and_marks_nothing(sessions, setup):
    calls, itinerary_id = setup
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value="none"))
        s.commit()
        assert travel_day.send_travel_days(s, NOW, BASE) == 0
    assert calls == []
    assert _marked(sessions, itinerary_id) is None


def test_the_daily_loop_sends_the_travel_day_message(migrated_url, setup):
    calls, _ = setup
    backup._remind(migrated_url, NOW)
    assert len(calls) == 1
    assert calls[0][0] == "Tomorrow 08:15 Amsterdam Centraal → 16:02 Zürich HB"
