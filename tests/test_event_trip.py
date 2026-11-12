"""Make a trip and its return trip from an uploaded .ics event (#2494)."""

import re
from datetime import date, datetime, time, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth import make_password_hash, token_limiter
from app.main import app
from app.models import Trip
from app.web import event_trip

PASSWORD = "pw"


def ics(*lines: str) -> bytes:
    return "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", *lines, "END:VCALENDAR", ""]).encode()


def event(*props: str) -> bytes:
    return ics("BEGIN:VEVENT", *props, "END:VEVENT")


TEAM_DAY = event("SUMMARY:Team day", "LOCATION:Berlin", "DTSTART;TZID=Europe/Berlin:20261221T100000",
                 "DTEND;TZID=Europe/Berlin:20261221T170000")


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    token_limiter.reset()
    monkeypatch.setattr(event_trip, "clock", lambda: datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc))
    yield
    token_limiter.reset()


def login(c):
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    login(c)
    return c


def csrf(c):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get("/trips/new").text).group(1)


def upload(c, data, origin="Amsterdam", margin="60", token=None):
    return c.post("/trips/from-event", data={"csrf_token": token or csrf(c), "origin_text": origin, "margin": margin},
                  files={"file": ("e.ics", data, "text/calendar")}, follow_redirects=False)


def trips(sessions):
    with sessions() as s:
        return s.scalars(select(Trip).order_by(Trip.id)).all()


def count(sessions):
    with sessions() as s:
        return s.scalar(select(func.count(Trip.id)))


def test_team_day_makes_the_trip_and_its_return(client, sessions):
    r = upload(client, TEAM_DAY)
    first, back = trips(sessions)
    assert r.status_code == 303 and r.headers["location"] == f"/trips/{first.id}/edit"
    assert (first.title, first.origin_text, first.destination_text) == ("Team day", "Amsterdam", "Berlin")
    assert (first.date_from, first.date_to, first.arrive_by, first.leave_after) == (
        date(2026, 12, 21), date(2026, 12, 21), time(9, 0), None)
    assert (back.title, back.origin_text, back.destination_text, back.return_of_id) == (
        "Team day (return)", "Berlin", "Amsterdam", first.id)
    assert (back.date_from, back.date_to, back.leave_after, back.arrive_by) == (
        date(2026, 12, 21), date(2026, 12, 21), time(17, 0), None)
    page = client.get(r.headers["location"])
    assert page.status_code == 200 and 'value="09:00"' in page.text and "UTC times" not in page.text


def test_margin_moves_the_arrival_to_the_day_before(client, sessions):
    data = event("SUMMARY:Early", "LOCATION:Paris", "DTSTART;TZID=Europe/Paris:20261221T013000",
                 "DTEND;TZID=Europe/Paris:20261221T120000")
    upload(client, data, margin="120")
    first, back = trips(sessions)
    assert (first.date_from, first.date_to, first.arrive_by) == (date(2026, 12, 20), date(2026, 12, 20), time(23, 30))
    assert (back.date_from, back.leave_after) == (date(2026, 12, 21), time(12, 0))


def test_all_day_event_has_days_only(client, sessions):
    data = event("SUMMARY:Fair", "LOCATION:Milan", "DTSTART;VALUE=DATE:20261221", "DTEND;VALUE=DATE:20261224")
    upload(client, data)
    first, back = trips(sessions)
    assert (first.date_from, first.date_to, first.arrive_by) == (date(2026, 12, 21), date(2026, 12, 21), None)
    assert (back.date_from, back.date_to, back.leave_after) == (date(2026, 12, 23), date(2026, 12, 23), None)


def test_empty_origin_location_and_summary(client, sessions):
    data = event("DTSTART;TZID=Europe/Berlin:20261221T100000")
    assert upload(client, data, origin="  ").status_code == 303
    first, back = trips(sessions)
    assert (first.title, first.origin_text, first.destination_text) == ("Event", None, None)
    assert (back.title, back.origin_text, back.destination_text) == ("Event (return)", None, None)


def test_utc_times_show_a_note(client, sessions):
    r = upload(client, event("SUMMARY:Call", "DTSTART:20261221T100000Z"))
    assert "The event file gave UTC times" in client.get(r.headers["location"]).text


@pytest.mark.parametrize("data, reason", [
    (ics("BEGIN:VTODO", "END:VTODO"), "The file has no event."),
    (event("DTSTART;TZID=Europe/Berlin:20250101T100000"), "The event starts in the past."),
    (b"\xff\xfe\x00bad", "The file is not UTF-8 text."),
    (b"x" * (256 * 1024 + 1), "The file is larger than 256 kB."),
])
def test_bad_file_makes_no_trip(client, sessions, data, reason):
    r = upload(client, data)
    assert r.status_code == 422 and reason in r.text and count(sessions) == 0


@pytest.mark.parametrize("margin", ["-1", "601", "abc", "1.5"])
def test_bad_margin_makes_no_trip(client, sessions, margin):
    r = upload(client, TEAM_DAY, margin=margin)
    assert r.status_code == 422 and "margin" in r.text and count(sessions) == 0


def test_bad_csrf_token_makes_no_trip(client, sessions):
    assert upload(client, TEAM_DAY, token="wrong").status_code in (400, 403)
    assert count(sessions) == 0


def test_login_is_needed(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    r = c.post("/trips/from-event", data={"csrf_token": "x"}, files={"file": ("e.ics", TEAM_DAY)},
               follow_redirects=False)
    assert r.status_code in (303, 401, 403) and count(sessions) == 0


def test_form_section_only_on_the_new_trip_form(client, sessions):
    assert 'action="/trips/from-event"' in client.get("/trips/new").text
    upload(client, TEAM_DAY)
    first = trips(sessions)[0]
    assert 'action="/trips/from-event"' not in client.get(f"/trips/{first.id}/edit").text
