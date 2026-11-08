"""Messages when a source fails, and when it works again (#1172). The rows of the captures are made in the database."""

from datetime import UTC, datetime, timedelta

from app import notify
from app.models import Capture, Setting, Trip
from app.sourcehealth import source_alert_messages

BASE = "https://trips.example"
T0 = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)
LINK = "https://trips.example/captures?failed=1&source=bahn.de"


def _cap(trip_id, hours, ok):
    return Capture(trip_id=trip_id, source="bahn.de", parser_version="1.1.0", captured_at=T0 + timedelta(hours=hours),
                   offer_count=3 if ok else 0, rejected_count=0, unreadable=None if ok else "no JSON")


def _add(sessions, captures):
    with sessions() as s:
        trip = Trip(title="Reise")
        s.add(trip)
        s.flush()
        s.add_all([_cap(trip.id, h, ok) for h, ok in captures])
        s.commit()


def _channel(sessions, channel):
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value=channel))
        s.merge(Setting(key=notify.NTFY_URL_KEY, value="https://ntfy.example/topic"))
        s.commit()


def _call(sessions):
    with sessions() as s:
        msgs = source_alert_messages(s, BASE)
        s.commit()
    return msgs


def _rows(sessions):
    with sessions() as s:
        return [r.key for r in s.query(Setting).filter(Setting.key.startswith("source_alert:"))]


def test_two_failed_captures_give_one_message_with_the_link(sessions):
    _channel(sessions, "ntfy")
    _add(sessions, [(0, True), (1, False), (2, False)])
    msgs = _call(sessions)
    assert [m.title for m in msgs] == ["bahn.de: the last 2 captures failed"]
    assert LINK in msgs[0].text and msgs[0].click == LINK
    assert _rows(sessions) == ["source_alert:bahn.de"]


def test_a_third_failed_capture_gives_no_message(sessions):
    _channel(sessions, "ntfy")
    _add(sessions, [(0, True), (1, False), (2, False)])
    _call(sessions)
    _add(sessions, [(3, False)])
    assert _call(sessions) == []
    assert _rows(sessions) == ["source_alert:bahn.de"]


def test_a_good_capture_gives_works_again_once(sessions):
    _channel(sessions, "ntfy")
    _add(sessions, [(0, True), (1, False), (2, False)])
    _call(sessions)
    _add(sessions, [(3, True)])
    msgs = _call(sessions)
    assert [m.title for m in msgs] == ["bahn.de works again"]
    assert _rows(sessions) == []
    assert _call(sessions) == []


def test_channel_none_gives_no_message_and_stores_no_row(sessions):
    _channel(sessions, "none")
    _add(sessions, [(0, True), (1, False), (2, False)])
    assert _call(sessions) == []
    assert _rows(sessions) == []
    _add(sessions, [(3, True)])
    assert _call(sessions) == []
    assert _rows(sessions) == []
