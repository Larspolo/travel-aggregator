"""Reader of the first event of an .ics file (#2493): the cases of #2492."""

from datetime import date, datetime, timezone

import pytest

from app.event_ics import EventError, read_event

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)


def ics(*event: str, head: str = "") -> bytes:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", *([head] if head else []), "BEGIN:VEVENT", *event,
             "END:VEVENT", "END:VCALENDAR", ""]
    return "\r\n".join(lines).encode()


TEAM_DAY = ics(
    "SUMMARY:Team day", "LOCATION:Berlin",
    "DTSTART;TZID=Europe/Berlin:20261221T100000", "DTEND;TZID=Europe/Berlin:20261221T170000",
)


def test_team_day():
    ev = read_event(TEAM_DAY, NOW)
    assert (ev.summary, ev.location, ev.utc) == ("Team day", "Berlin", False)
    assert ev.start == datetime(2026, 12, 21, 10, 0)
    assert ev.end == datetime(2026, 12, 21, 17, 0)


def test_folded_lines_and_lf():
    data = b"BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Team\n  day\nLOCATION:Ber\n\tlin\nDTSTART:20261221T100000\nEND:VEVENT\n"
    ev = read_event(data, NOW)
    assert (ev.summary, ev.location) == ("Team day", "Berlin")


def test_text_escapes():
    ev = read_event(ics(r"SUMMARY:A\, B\; C\\D\nE", "DTSTART:20261221T100000"), NOW)
    assert ev.summary == "A, B; C\\D\nE"


def test_floating():
    ev = read_event(ics("DTSTART:20261221T100000", "DTEND:20261221T120000"), NOW)
    assert (ev.start, ev.end, ev.utc) == (datetime(2026, 12, 21, 10), datetime(2026, 12, 21, 12), False)


def test_utc_without_calendar_zone():
    ev = read_event(ics("DTSTART:20261221T090000Z", "DTEND:20261221T160000Z"), NOW)
    assert (ev.start, ev.end, ev.utc) == (datetime(2026, 12, 21, 9), datetime(2026, 12, 21, 16), True)


def test_utc_with_calendar_zone():
    data = ics("DTSTART:20261221T090000Z", "DTEND:20261221T160000Z", head="X-WR-TIMEZONE:Europe/Berlin")
    ev = read_event(data, NOW)
    assert (ev.start, ev.end, ev.utc) == (datetime(2026, 12, 21, 10), datetime(2026, 12, 21, 17), False)


def test_all_day_end_is_exclusive():
    ev = read_event(ics("DTSTART;VALUE=DATE:20261221", "DTEND;VALUE=DATE:20261223"), NOW)
    assert (ev.start, ev.end) == (date(2026, 12, 21), date(2026, 12, 22))


def test_all_day_one_day():
    ev = read_event(ics("DTSTART;VALUE=DATE:20261221", "DTEND;VALUE=DATE:20261222"), NOW)
    assert ev.start == ev.end == date(2026, 12, 21)


def test_duration_hours():
    ev = read_event(ics("DTSTART:20261221T100000", "DURATION:PT2H"), NOW)
    assert ev.end == datetime(2026, 12, 21, 12)


def test_duration_day_all_day():
    ev = read_event(ics("DTSTART;VALUE=DATE:20261221", "DURATION:P1D"), NOW)
    assert ev.end == date(2026, 12, 21)


def test_no_end():
    ev = read_event(ics("DTSTART:20261221T100000"), NOW)
    assert ev.end == ev.start


def test_rrule_and_alarm_and_timezone_ignored():
    data = ics(
        "SUMMARY:Weekly", "DTSTART;TZID=Europe/Berlin:20261221T100000", "RRULE:FREQ=WEEKLY",
        "BEGIN:VALARM", "TRIGGER:-PT15M", "SUMMARY:Alarm", "END:VALARM",
        head="BEGIN:VTIMEZONE\r\nTZID:Europe/Berlin\r\nBEGIN:STANDARD\r\nDTSTART:19701025T030000\r\nEND:STANDARD\r\nEND:VTIMEZONE",
    )
    ev = read_event(data, NOW)
    assert (ev.summary, ev.start) == ("Weekly", datetime(2026, 12, 21, 10))


def test_first_event_only():
    data = TEAM_DAY.replace(b"END:VCALENDAR", b"BEGIN:VEVENT\r\nSUMMARY:Second\r\nDTSTART:20261222T100000\r\nEND:VEVENT\r\nEND:VCALENDAR")
    assert read_event(data, NOW).summary == "Team day"


def test_long_text_is_cut():
    ev = read_event(ics("SUMMARY:" + "x" * 300, "DTSTART:20261221T100000"), NOW)
    assert len(ev.summary) == 200 and ev.location is None


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", "The file has no event."),
        (ics("SUMMARY:x"), "The event has no start."),
        (ics("DTSTART:20261101T100000"), "The event starts in the past."),
        (ics("DTSTART;VALUE=DATE:20261111"), "The event starts in the past."),
        (ics("SUMMARY:\xe9", "DTSTART:20261221T100000").replace(b"\xc3\xa9", b"\xe9"), "The file is not UTF-8 text."),
        (b"X" * (256 * 1024 + 1), "The file is larger than 256 kB."),
    ],
)
def test_errors(data, reason):
    with pytest.raises(EventError) as err:
        read_event(data, NOW)
    assert err.value.reason == reason
