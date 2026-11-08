"""The bahn.de day prices on the days of the trip page (#1198): only a day with no captured connection shows one."""

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.days import Day, with_day_prices
from tests.test_trip_days_strip import _on, _set_range, _strip
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)


def _price(sessions, tid, day, amount):
    from app.models import DayPrice
    with sessions() as s:
        s.add(DayPrice(source="bahn.de", trip_id=tid, day=day, price=Decimal(amount), currency="EUR",
                       captured_at=datetime(2026, 11, 1, tzinfo=timezone.utc)))
        s.commit()


def test_with_day_prices_sets_only_days_with_no_row():
    row = object()
    days = [Day("2026-12-19", row, row, 1), Day("2026-12-20", None, None, 0), Day("2026-12-21", None, None, 0)]
    p = [SimpleNamespace(day=date(2026, 12, d), price=Decimal(v)) for d, v in ((19, "10"), (20, "50"), (20, "39"))]
    out = with_day_prices(days, p)
    assert out[0].day_price is None
    assert out[1].day_price.price == Decimal("39")
    assert out[2].day_price is None


def test_strip_shows_day_price_only_on_a_day_with_no_connection(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _set_range(sessions, tid, date(2026, 12, 19), date(2026, 12, 21))
    ingest(client, auth, tid, [_on("2026-12-19", "89.90", "ICE 1")])
    _price(sessions, tid, date(2026, 12, 19), "19.00")
    _price(sessions, tid, date(2026, 12, 20), "39.00")
    strip = _strip(client.get(f"/trips/{tid}").text)
    assert "from €39.00 (bahn.de day price)" in strip
    assert "€19.00" not in strip  # a day with connections does not change
    assert strip.count('class="day-best"') == 1
    assert "no offers" in strip  # the 21st has no day price
