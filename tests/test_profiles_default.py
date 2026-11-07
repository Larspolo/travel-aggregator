"""The trip page ranks with the default profile when the URL has no weights; a weight in the URL wins (#230)."""

from datetime import time
from decimal import Decimal

from app.models import ScoreProfile
from app.profiles import active_weights, to_config
from app.ranking import Weights
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

# offer("89.90"): 472 minutes, 1 transfer; direct("150.00"): 240 minutes, no transfer


def _default_profile(sessions, **weights):
    with sessions() as s:
        s.add(ScoreProfile(name="Fast", is_default=True, config_json=to_config(Weights(**weights))))
        s.commit()


def _first_is_direct(page):
    return page.index("ICE 9") < page.index("ICE 105")


def test_a_url_weight_replaces_only_its_field():
    base = Weights(hour_markup=Decimal("50"), night_hour_markup=Decimal("4"))
    w = active_weights(base, {"hour_markup": Decimal("0"), "transfer_markup": None, "night_start": time(22, 0)})
    assert (w.hour_markup, w.transfer_markup, w.night_start, w.night_hour_markup) == (
        Decimal("0"), Decimal("10"), time(22, 0), Decimal("4"))
    assert active_weights(base, {}) == base and active_weights(Weights(), {"night_hour_markup": None}).night_hour_markup is None


def test_the_default_profile_ranks_and_a_url_weight_wins(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _default_profile(sessions, hour_markup=Decimal("50"))
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    page = client.get(f"/trips/{trip_id}").text
    assert "€150 price + €200 time = €350" in page and _first_is_direct(page)  # 240 min × 50/60
    assert 'name="hour_markup" min="0" max="100" step="1" value="50"' in page
    page = client.get(f"/trips/{trip_id}?hour_markup=0").text
    assert "= €99.90" in page and not _first_is_direct(page)  # 89.90 + 1 transfer × 10


def test_with_no_default_profile_the_page_ranks_as_before(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    with sessions() as s:
        s.add(ScoreProfile(name="Other", is_default=False, config_json={"hour_markup": "50"}))
        s.commit()
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    page = client.get(f"/trips/{trip_id}").text
    assert "= €210" in page and "= €217.90" in page and _first_is_direct(page)


def test_a_sort_link_keeps_the_values_of_the_default_profile(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _default_profile(sessions, hour_markup=Decimal("50"), night_start=time(22, 15))
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    page = client.get(f"/trips/{trip_id}").text
    link = page[page.index('<a class="sort"'):]
    link = link[:link.index('">')]
    assert "hour_markup=50" in link and "night_start=22%3A15" in link and "transfer_markup=10" in link
    assert "night_hour_markup" not in link  # None: the same as hour_markup
    page = client.get(f"/trips/{trip_id}?hour_markup=0&sort=price").text
    link = page[page.index('<a class="sort"'):]
    assert "hour_markup=0&amp;" in link[:link.index('">')]
