"""The trip table shows a mode icon per leg mode, a '+N day' mark and the age of the newest capture (#111)."""

import copy
import re
from datetime import datetime, timedelta, timezone

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from app.web.pages import ago, day_gap, mode_icon


def test_each_mode_has_an_icon_and_an_unknown_mode_a_dot():
    assert mode_icon("train") == "train" and mode_icon("bus") == "bus" and mode_icon("flight") == "plane"
    assert mode_icon("boat") == ""


def test_day_gap_counts_local_calendar_days():
    depart = datetime(2026, 12, 20, 23, 0, tzinfo=timezone.utc)
    assert day_gap(datetime(2026, 12, 21, 1, 0, tzinfo=timezone.utc), depart) == 1
    assert day_gap(datetime(2026, 12, 22, 0, 30, tzinfo=timezone.utc), depart) == 2
    assert day_gap(datetime(2026, 12, 20, 23, 59, tzinfo=timezone.utc), depart) == 0


def test_ago_gives_minutes_hours_and_days():
    now = datetime(2026, 12, 20, 12, 0, tzinfo=timezone.utc)
    assert ago(now - timedelta(minutes=5), now) == "5 min ago"
    assert ago(now - timedelta(hours=2), now) == "2 h ago"
    assert ago(now - timedelta(days=3), now) == "3 days ago"


def test_the_row_shows_icons_the_day_mark_and_the_capture_age(trip):  # noqa: F811
    client, auth, trip_id = trip
    o = copy.deepcopy(offer("89.90"))
    train, bus = o["legs"][0], dict(o["legs"][0])
    train.update(mode="train", depart_at="2026-12-20T22:00:00+01:00", arrive_at="2026-12-20T23:30:00+01:00")
    bus.update(mode="bus", depart_at="2026-12-20T23:45:00+01:00", arrive_at="2026-12-21T01:00:00+01:00")
    o["legs"] = [train, bus]
    ingest(client, auth, trip_id, [o])
    page = client.get(f"/trips/{trip_id}").text
    assert "icons.svg#train" in page and "icons.svg#bus" in page
    assert "+1 day" in page and "+2 days" not in page
    assert re.search(r"\d+ (min|h|days?) ago", page)
