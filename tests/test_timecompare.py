"""A night train and a day train of one trip compare on effective cost (#144, whole check of #140)."""

import copy

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def _night(price):
    """22:00 → 06:00 the next day: 8 hours, 420 night minutes, no transfer."""
    o = copy.deepcopy(offer(price, "NJ 40"))
    o["legs"] = [dict(o["legs"][0], to_name="Zürich HB", depart_at="2026-12-20T22:00:00+01:00",
                      arrive_at="2026-12-21T06:00:00+01:00")]
    return o


def test_day_train_first_without_night_bonus(trip):  # noqa: F811
    client, auth, trip_id = trip
    # Day: 150 + 240 min × 15/60 = 210. Night: 100 + 480 min × 15/60 = 220.
    ingest(client, auth, trip_id, [_night("100.00"), direct("150.00")])
    page = client.get(f"/trips/{trip_id}?night_adjust=0").text
    assert page.index("= €210") < page.index("= €220")


def test_night_train_first_with_a_large_night_bonus(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_night("100.00"), direct("150.00")])
    page = client.get(f"/trips/{trip_id}?night_adjust=-20").text
    # Night: 220 - 20 = 200, which is below the day train's 210.
    assert page.index("= €200") < page.index("= €210")


def test_breakdown_of_the_night_train_shows_the_night_part(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_night("100.00"), direct("150.00")])
    page = client.get(f"/trips/{trip_id}?night_adjust=-20").text
    assert "€-20 night travel" in page
    assert "€-20 night travel" not in client.get(f"/trips/{trip_id}?night_adjust=0").text
