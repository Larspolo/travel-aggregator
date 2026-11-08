"""The best offer of a trip for each profile (#1210): `best_by_profile()` gives the first row of the ranked table of
each profile, with the same effective cost."""

from decimal import Decimal

from app.models import Itinerary, ScoreProfile, Trip
from app.profile_compare import best_by_profile
from app.profiles import to_config
from app.ranking import Weights
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

# offer("89.90"): 472 minutes, 1 transfer (the slow cheap one); direct("150.00"): 240 minutes, no transfer


def _profiles(sessions):
    with sessions() as s:
        s.add(ScoreProfile(name="Cheap", is_default=True, config_json=to_config(Weights(hour_markup=Decimal("2")))))
        s.add(ScoreProfile(name="Comfort", is_default=False, config_json=to_config(Weights(hour_markup=Decimal("30")))))
        s.commit()


def _best(sessions, trip_id):
    with sessions() as s:
        return [(b.profile.name, b.itinerary.transfers if b.itinerary else None, b.breakdown.total if b.breakdown else None)
                for b in best_by_profile(s, s.get(Trip, trip_id))]


def test_each_profile_gets_its_own_best_offer(trip, sessions):  # noqa: F811
    client_, auth, trip_id = trip
    ingest(client_, auth, trip_id, [offer("89.90"), direct("150.00")])
    _profiles(sessions)
    cheap = Decimal("89.90") + Decimal(472) / 60 * 2 + 10  # price + hours × €2 + 1 transfer × €10
    comfort = Decimal("150.00") + 4 * 30
    assert _best(sessions, trip_id) == [("Cheap", 1, cheap.quantize(Decimal("0.01"))), ("Comfort", 0, comfort)]
    with sessions() as s:  # the same totals as the ranked table of each profile
        ids = {p.name: p.id for p in s.query(ScoreProfile)}
    for name, total in (("Cheap", cheap), ("Comfort", comfort)):
        page = client_.get(f"/trips/{trip_id}", params={"profile": ids[name]}).text
        assert f"{total.quantize(Decimal('0.01')):.2f}" in page.replace(",", ".")


def test_no_visible_itinerary_gives_no_itinerary(trip, sessions):  # noqa: F811
    client_, auth, trip_id = trip
    ingest(client_, auth, trip_id, [offer("89.90")])
    _profiles(sessions)
    with sessions() as s:
        for it in s.query(Itinerary).filter_by(trip_id=trip_id):
            it.hidden = True
        s.commit()
    assert _best(sessions, trip_id) == [("Cheap", None, None), ("Comfort", None, None)]


def test_a_trip_with_no_offers_gives_no_itinerary(trip, sessions):  # noqa: F811
    _, _, trip_id = trip
    _profiles(sessions)
    assert _best(sessions, trip_id) == [("Cheap", None, None), ("Comfort", None, None)]
