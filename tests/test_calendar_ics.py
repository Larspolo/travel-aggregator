from datetime import datetime, timezone

from app.calendar_ics import itinerary_ics
from app.models import Itinerary, Leg, Trip

CRLF = "\r\n"
NOW = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)


def _leg(seq, carrier, service_no, from_name, to_name, depart_utc, arrive_utc, depart_off, arrive_off):
    return Leg(
        id=10 + seq,
        seq=seq,
        mode="train",
        carrier=carrier,
        service_no=service_no,
        from_name=from_name,
        to_name=to_name,
        depart_at=depart_utc,
        depart_offset_min=depart_off,
        arrive_at=arrive_utc,
        arrive_offset_min=arrive_off,
    )


def _itinerary_of(legs):
    trip = Trip(id=1, title="Christmas trip")
    itinerary = Itinerary(id=1, trip_id=1, fingerprint="f", duration_min=0, legs=legs)
    trip.itineraries = [itinerary]
    return trip, itinerary


def _unfold(text):
    return text.replace(CRLF + " ", "")


def _physical_lines(text):
    return text.split(CRLF)[:-1]


def test_two_legs_give_two_events_with_utc_times_and_local_text():
    legs = [
        _leg(
            2,
            "DB",
            "ICE 1",
            "Berlin Hbf",
            "Hamburg",
            datetime(2026, 12, 20, 11, 0, tzinfo=timezone.utc),
            datetime(2026, 12, 20, 12, 0, tzinfo=timezone.utc),
            60,
            60,
        ),
        _leg(
            1,
            "NS",
            "123",
            "Amsterdam Centraal",
            "Berlin Hbf",
            datetime(2026, 12, 20, 7, 12, tzinfo=timezone.utc),
            datetime(2026, 12, 20, 13, 30, tzinfo=timezone.utc),
            60,
            60,
        ),
    ]
    trip, itinerary = _itinerary_of(legs)

    text = itinerary_ics(trip, itinerary, NOW)
    unfolded = _unfold(text)

    assert unfolded.count("BEGIN:VEVENT") == 2
    assert unfolded.index("UID:leg-11@") < unfolded.index("UID:leg-12@")  # seq order
    assert "DTSTART:20261220T071200Z" in unfolded
    assert "DTEND:20261220T133000Z" in unfolded
    assert "DTSTAMP:20261201T090000Z" in unfolded
    assert "SUMMARY:NS 123: Amsterdam Centraal → Berlin Hbf" in unfolded
    assert "SUMMARY:DB ICE 1: Berlin Hbf → Hamburg" in unfolded
    assert "LOCATION:Amsterdam Centraal" in unfolded
    assert (
        "DESCRIPTION:Departs 08:12 (UTC+01:00) at Amsterdam Centraal\\n"
        "Arrives 14:30 (UTC+01:00) at Berlin Hbf\\nTrip: Christmas trip"
    ) in unfolded


def test_empty_carrier_and_service_number_are_left_out():
    legs = [
        _leg(
            1,
            "",
            None,
            "Lyon",
            "Nice",
            datetime(2026, 12, 20, 7, 0, tzinfo=timezone.utc),
            datetime(2026, 12, 20, 9, 0, tzinfo=timezone.utc),
            60,
            60,
        )
    ]
    trip, itinerary = _itinerary_of(legs)

    unfolded = _unfold(itinerary_ics(trip, itinerary, NOW))

    assert "SUMMARY:Lyon → Nice" in unfolded


def test_special_characters_in_place_names_are_escaped():
    legs = [
        _leg(
            1,
            "NS",
            "1",
            "Den Haag, Centraal; \\ x\nnew",
            "Delft",
            datetime(2026, 12, 20, 7, 0, tzinfo=timezone.utc),
            datetime(2026, 12, 20, 8, 0, tzinfo=timezone.utc),
            60,
            60,
        )
    ]
    trip, itinerary = _itinerary_of(legs)

    unfolded = _unfold(itinerary_ics(trip, itinerary, NOW))

    assert "LOCATION:Den Haag\\, Centraal\\; \\\\ x\\nnew" in unfolded
    assert "SUMMARY:NS 1: Den Haag\\, Centraal\\; \\\\ x\\nnew → Delft" in unfolded


def test_long_summary_is_folded_to_75_octets_and_unfolds_to_the_same_text():
    from_name = "ü→" * 50  # 100 characters, 2 bytes for ü and 3 bytes for →
    legs = [
        _leg(
            1,
            "",
            "",
            from_name,
            "Berlin",
            datetime(2026, 12, 20, 7, 0, tzinfo=timezone.utc),
            datetime(2026, 12, 20, 8, 0, tzinfo=timezone.utc),
            60,
            60,
        )
    ]
    trip, itinerary = _itinerary_of(legs)

    text = itinerary_ics(trip, itinerary, NOW)

    for line in _physical_lines(text):
        assert len(line.encode("utf-8")) <= 75
    summary_lines = [line for line in text.split(CRLF) if line.startswith("SUMMARY:") or line.startswith(" ")]
    summary = _unfold(text).split("SUMMARY:")[1].split(CRLF)[0]
    assert summary == f"{from_name} → Berlin"
    assert len(summary_lines) > 1  # the summary is really folded


def test_every_line_ends_with_crlf():
    legs = [
        _leg(
            1,
            "NS",
            "1",
            "A",
            "B",
            datetime(2026, 12, 20, 7, 0, tzinfo=timezone.utc),
            datetime(2026, 12, 20, 8, 0, tzinfo=timezone.utc),
            60,
            60,
        )
    ]
    trip, itinerary = _itinerary_of(legs)

    text = itinerary_ics(trip, itinerary, NOW)

    assert text.endswith("END:VCALENDAR" + CRLF)
    assert "\n" not in text.replace(CRLF, "")
