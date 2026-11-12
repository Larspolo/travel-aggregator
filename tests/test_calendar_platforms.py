from datetime import datetime, timezone

from app.calendar_ics import itinerary_ics
from app.models import Itinerary, Leg, Trip

CRLF = "\r\n"
NOW = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)


def _leg(from_platform=None, to_platform=None):
    return Leg(
        id=11,
        seq=1,
        mode="train",
        carrier="NS",
        service_no="123",
        from_name="Amsterdam Centraal",
        to_name="Berlin Hbf",
        depart_at=datetime(2026, 12, 20, 7, 12, tzinfo=timezone.utc),
        depart_offset_min=60,
        arrive_at=datetime(2026, 12, 20, 11, 0, tzinfo=timezone.utc),
        arrive_offset_min=60,
        from_platform=from_platform,
        to_platform=to_platform,
    )


def _ics(leg):
    trip = Trip(id=1, title="Christmas trip")
    itinerary = Itinerary(id=1, trip_id=1, fingerprint="f", duration_min=0, legs=[leg])
    trip.itineraries = [itinerary]
    return itinerary_ics(trip, itinerary, NOW)


def _unfold(text):
    return text.replace(CRLF + " ", "")


def test_platforms_are_named_in_location_and_description():
    text = _unfold(_ics(_leg(from_platform="8b", to_platform="4")))
    assert "LOCATION:Amsterdam Centraal\\, platform 8b" + CRLF in text
    assert "Departs 08:12 (UTC+01:00) at Amsterdam Centraal (platform 8b)" in text
    assert "Arrives 12:00 (UTC+01:00) at Berlin Hbf (platform 4)" in text


def test_only_the_known_platform_is_named():
    text = _unfold(_ics(_leg(from_platform="8b")))
    assert "LOCATION:Amsterdam Centraal\\, platform 8b" + CRLF in text
    assert "at Amsterdam Centraal (platform 8b)" in text
    assert "at Berlin Hbf" in text
    assert "Berlin Hbf (platform" not in text


def test_leg_without_platforms_gives_the_plain_place():
    text = _unfold(_ics(_leg()))
    assert "LOCATION:Amsterdam Centraal" + CRLF in text
    assert "platform" not in text
    assert "at Amsterdam Centraal\\nArrives" in text
    assert "at Berlin Hbf\\nTrip" in text
