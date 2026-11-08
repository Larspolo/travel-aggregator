"""One split ticket from the captures to the trip page and the trips list (#1181, epic of #1177-#1180): the offers of
the two split trips come in through the ingest API, the trip page shows the best pair, a too short transfer does not
show, and the active profile changes the order of the pairs."""

import copy
import re
from decimal import Decimal

from sqlalchemy import select

from app.models import ScoreProfile, Trip
from app.profiles import to_config
from app.ranking import Weights
from tests.test_ingest_api import BODY
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture: a logged-in client and an empty trip)

DAY = "2026-12-20"


def _leg(frm, to, depart, arrive, service, carrier):
    return {"mode": "train", "carrier": carrier, "service_no": service, "from_name": frm, "to_name": to,
            "depart_at": f"{DAY}T{depart}:00+01:00", "arrive_at": f"{DAY}T{arrive}:00+01:00"}


def _offer(price, frm, to, depart, arrive, service="ICE 105", carrier="DB"):
    o = copy.deepcopy(BODY["offers"][0])
    o.update(price_amount=price, fare_name="Sparpreis", legs=[_leg(frm, to, depart, arrive, service, carrier)])
    return o


def _ingest(client, auth, trip_id, source, offers):
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, source=source, offers=offers)
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text


def _split(client, trip_id):
    """Split the trip via Köln (the form of the trip page, #1177)."""
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)
    r = client.post(f"/trips/{trip_id}/split", data={"via": "Köln", "csrf_token": token}, follow_redirects=False)
    assert r.status_code == 303, r.text


def _split_ids(sessions, trip_id):
    with sessions() as s:
        return [t.id for t in s.get(Trip, trip_id).split_trips]


def _section_html(page):
    start = page.index("Split tickets via Köln")
    return page[start:page.index("</section>", start)]


def _section(page):
    """The text of the split section of the trip page (#1179)."""
    return re.sub(r"<[^>]+>", " ", _section_html(page))


def _profiles(sessions):
    with sessions() as s:
        s.add(ScoreProfile(name="Cheap", is_default=False, config_json=to_config(Weights(hour_markup=Decimal("0")))))
        s.add(ScoreProfile(name="Fast", is_default=False, config_json=to_config(Weights(hour_markup=Decimal("50")))))
        s.commit()
        return {p.name: p.id for p in s.scalars(select(ScoreProfile))}


def _set_trip_profile(sessions, trip_id, profile_id):
    with sessions() as s:
        s.get(Trip, trip_id).profile_id = profile_id
        s.commit()


def _fill(client, auth, sessions, trip_id):
    """The direct offer and the offers of both split trips. Two pairs connect; one B offer leaves 5 minutes, too short."""
    _split(client, trip_id)
    a, b = _split_ids(sessions, trip_id)
    _ingest(client, auth, trip_id, "bahn.de", [_offer("200.00", "Amsterdam Centraal", "Zürich HB", "07:00", "15:00")])
    _ingest(client, auth, a, "ns", [
        _offer("40.00", "Amsterdam Centraal", "Köln Hbf", "07:00", "10:00", "ICE 21", "DB"),  # arrives 10:00
        _offer("25.00", "Amsterdam Centraal", "Köln Hbf", "07:00", "12:00", "IC 23", "NS"),  # arrives 12:00
    ])
    _ingest(client, auth, b, "db", [
        _offer("50.00", "Köln Hbf", "Zürich HB", "11:00", "14:00", "ICE 9", "DB"),  # 60 min after 10:00
        _offer("35.00", "Köln Hbf", "Zürich HB", "13:00", "19:00", "ICE 10", "DB"),  # 60 min after 12:00
        _offer("1.00", "Köln Hbf", "Zürich HB", "10:05", "10:50", "RE 2", "DB"),  # 5 min after 10:00: too short
    ])
    return a, b


def test_the_trip_page_shows_the_best_pair_and_the_difference_to_the_direct_offer(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _fill(client, auth, sessions, trip_id)
    section = _section(client.get(f"/trips/{trip_id}").text)
    # the best pair under the default profile: the 07:00 train to Köln (arrives 10:00) and the 11:00 train to Zürich
    assert "Split tickets via Köln" in section
    assert "Sun 20 Dec 07:00 → Sun 20 Dec 14:00" in section
    assert "1 h 00 min transfer" in section
    assert "less than the best direct offer" in section
    # the too short transfer (5 min after 10:00, arrives 10:50) does not show
    assert "10:50" not in section


def test_the_trips_list_shows_the_split_trips_under_their_trip(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _fill(client, auth, sessions, trip_id)
    page = client.get("/").text
    assert page.count("split via Köln") == 2
    assert page.index("Amsterdam – Zürich") < page.index("split via Köln")


def _best_pair(page):
    """The time line of the first (best) pair of the split section."""
    return re.search(r"<strong>([^<]+)</strong>", _section_html(page)).group(1)


def test_a_change_of_the_active_profile_changes_the_order_of_the_pairs(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _fill(client, auth, sessions, trip_id)
    ids = _profiles(sessions)
    _set_trip_profile(sessions, trip_id, ids["Cheap"])
    cheap = _best_pair(client.get(f"/trips/{trip_id}").text)
    _set_trip_profile(sessions, trip_id, ids["Fast"])
    fast = _best_pair(client.get(f"/trips/{trip_id}").text)
    # no hour value: the 25 + 35 € pair (arrives 19:00) is the cheapest; a high hour value: the 40 + 50 € pair wins
    assert cheap == "Sun 20 Dec 07:00 → Sun 20 Dec 19:00"
    assert fast == "Sun 20 Dec 07:00 → Sun 20 Dec 14:00"
