"""The trips list shows a series of trips in one line (#2499); the search, the tags, the sort and the archive."""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Trip, TripSeries
from app.trips import TripRow, series_journeys
from tests.test_trip_forms import client, engine  # noqa: F401 (fixtures)


def _row(i, d, sid=1, status="planning", title="Amsterdam → Berlin"):
    return TripRow(id=i, title=title, origin_text="Amsterdam", destination_text="Berlin", date_from=d, date_to=None,
                   status=status, offer_count=0, best_price=None, best_currency=None, series_id=sid, series_step=2)


def test_four_trips_first_past_show_one_line_with_second_date():
    rows = [_row(i, date(2026, 12, 4) + timedelta(weeks=2 * (i - 1))) for i in range(1, 5)]
    lines = series_journeys([("trip", r, "") for r in rows], rows, date(2026, 12, 10))
    assert [(k, t.id, n) for k, t, n in lines] == [("series", 2, "every 2 weeks · next Fri 18 Dec · 4 trips")]


def test_all_past_gives_the_last_trip_and_others_stay():
    rows = [_row(1, date(2026, 1, 2)), _row(2, date(2026, 1, 16)), _row(3, date(2026, 1, 9), sid=None, title="Solo")]
    lines = series_journeys([("trip", r, "") for r in rows], rows, date(2026, 12, 1))
    assert [(k, t.id) for k, t, _ in lines] == [("series", 2), ("trip", 3)]


def test_archived_trip_does_not_count():
    rows = [_row(1, date(2026, 12, 4)), _row(2, date(2026, 12, 18)), _row(3, date(2027, 1, 1), status="archived")]
    lines = series_journeys([("trip", r, "") for r in rows[:2]], rows, date(2026, 12, 1))
    assert [n for _, _, n in lines] == ["every 2 weeks · next Fri 4 Dec · 2 trips"]


def _series(engine, n=4, **kw):  # noqa: F811
    with Session(engine) as s:
        series = TripSeries(step_weeks=2)
        s.add(series)
        s.flush()
        start = date.today() - timedelta(days=3)
        for k in range(n):
            s.add(Trip(title="Amsterdam → Berlin", origin_text="Amsterdam", destination_text="Berlin",
                       date_from=start + timedelta(weeks=2 * k), series_id=series.id, **kw))
        s.add(Trip(title="Utrecht → Paris", origin_text="Utrecht", destination_text="Paris", tags_text="work",
                   date_from=start))
        s.commit()


def test_page_search_tag_sort_and_archive(engine, client):  # noqa: F811
    _series(engine, tags_text="work")
    page = client.get("/").text
    assert page.count("4 trips") == 1 and page.count("Amsterdam → Berlin</a>") == 1 and "Utrecht → Paris" in page
    assert "4 trips" in client.get("/?q=berlin").text and "Utrecht → Paris" not in client.get("/?q=berlin").text
    assert "4 trips" in client.get("/?tag=work").text
    for key in ("price", "capture", "title"):
        assert client.get(f"/?sort={key}").text.count("4 trips") == 1
    with Session(engine) as s:
        for t in s.query(Trip).filter(Trip.series_id.is_not(None)):
            t.status = "archived"
        s.commit()
    arch = client.get("/?archived=1").text
    assert "4 trips" not in arch and arch.count("Amsterdam → Berlin</a>") == 4
