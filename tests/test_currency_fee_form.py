"""The currency fee in the trip page and in a profile (#1994): `currency_fee_pct` comes from the query and the
"Card fee for other currencies (%)" input of "Advanced", and a profile keeps it; the range is 0 to 10."""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import CurrencyRate, Fare, Itinerary, ScoreProfile
from app.profiles import from_config
from tests.test_trip_booked import csrf
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _chf_trip(client, auth, trip_id, sessions):
    """One offer of EUR 100 whose fare is in CHF at a rate of 1.00, so its EUR price is 100."""
    ingest(client, auth, trip_id, [offer("100.00", "ICE 1")])
    with sessions() as s:
        for f in s.scalars(select(Fare).join(Itinerary, Fare.itinerary_id == Itinerary.id).where(Itinerary.trip_id == trip_id)):
            f.currency, f.latest_price = "CHF", Decimal("100.00")
        s.add(CurrencyRate(code="CHF", eur_per_unit=Decimal("1.00"), updated_at=datetime.now(timezone.utc)))
        s.commit()


def _totals(page):
    return [line.rsplit("= €", 1)[1].split("<")[0].strip() for line in page.split("\n") if "= €" in line]


def test_a_chf_fare_shows_the_currency_fee_in_its_breakdown(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _chf_trip(client, auth, trip_id, sessions)
    default = client.get(f"/trips/{trip_id}").text
    assert "currency fee" not in default
    page = client.get(f"/trips/{trip_id}", params={"currency_fee_pct": "2"}).text
    assert "currency fee" in page
    assert _totals(page) == [str(Decimal(_totals(default)[0]) + 2)]
    assert 'name="currency_fee_pct"' in page and 'value="2"' in page


def test_a_saved_profile_loads_the_currency_fee(trip, sessions):  # noqa: F811
    client, _, trip_id = trip
    data = {"csrf_token": csrf(client, trip_id), "trip_id": trip_id, "name": "Abroad", "currency_fee_pct": "2"}
    r = client.post("/profiles", data=data, follow_redirects=False)
    assert r.status_code == 303
    with sessions() as s:
        assert from_config(s.query(ScoreProfile).one().config_json).currency_fee_pct == Decimal("2")


def test_a_value_above_10_is_rejected_on_the_trip_page(trip, sessions):  # noqa: F811
    client, _, trip_id = trip
    assert client.get(f"/trips/{trip_id}", params={"currency_fee_pct": "11"}).status_code == 422


def test_a_value_above_10_is_rejected_on_save(trip, sessions):  # noqa: F811
    client, _, trip_id = trip
    data = {"csrf_token": csrf(client, trip_id), "trip_id": trip_id, "name": "Abroad", "currency_fee_pct": "11"}
    assert client.post("/profiles", data=data, follow_redirects=False).status_code == 422
    with sessions() as s:
        assert s.query(ScoreProfile).count() == 0
