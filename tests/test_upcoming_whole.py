"""The whole Upcoming page (#861): two booked trips show in date order with all their legs, local times and calendar
links, through the ingest API and the booked action of the trip page. A not booked and a past booking do not show."""

import copy
from datetime import datetime, timedelta, timezone

from app.models import Trip
from tests.test_trip_manage_whole import _csrf, _id_at, _post
from tests.test_trip_page import BODY, ingest, trip  # noqa: F401  (trip is a fixture)

Y = datetime.now(timezone.utc).year + 1  # the dates stay in the future


def leg(day, service_no, carrier, from_name, to_name, depart, arrive):
    return {"mode": "train", "carrier": carrier, "service_no": service_no, "from_name": from_name, "to_name": to_name,
            "depart_at": f"{day}T{depart}:00+01:00", "arrive_at": f"{day}T{arrive}:00+01:00"}


def route(day, first_service, second_service):
    """The two legs of BODY: Amsterdam Centraal → Basel SBB → Zürich HB, on day (YYYY-MM-DD)."""
    return [leg(day, first_service, "DB", "Amsterdam Centraal", "Basel SBB", "07:34", "14:02"),
            leg(day, second_service, "SBB", "Basel SBB", "Zürich HB", "14:33", "15:26")]


def offer(price, legs):
    o = copy.deepcopy(BODY["offers"][0])
    o.update(price_amount=price)
    o["legs"] = legs
    return o


def new_trip(sessions, title):
    with sessions() as s:
        t = Trip(title=title, origin_text="Amsterdam", destination_text="Zürich")
        s.add(t)
        s.commit()
        return t.id


def test_the_upcoming_page_shows_the_booked_journeys_in_date_order(trip, sessions):  # noqa: F811
    client, auth, _ = trip
    day_a, day_b = f"{Y}-12-20", f"{Y}-12-10"
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    day_c = yesterday.strftime("%Y-%m-%d")

    trip_a = new_trip(sessions, "Trip A")
    trip_b = new_trip(sessions, "Trip B")
    trip_c = new_trip(sessions, "Trip C")

    # trip A: one booked offer and one offer that stays not booked, both on the 20th
    ingest(client, auth, trip_a, [offer("89.90", route(day_a, "ICE 105", "IC 61")),
                                  offer("99.90", route(day_a, "ICE 123", "IC 61"))])
    # trip B: booked, on the 10th, so it comes first
    ingest(client, auth, trip_b, [offer("79.90", route(day_b, "ICE 77", "IC 9"))])
    # trip C: booked, but it left yesterday
    ingest(client, auth, trip_c, [offer("69.90", route(day_c, "ICE 88", "IC 19"))])

    _post(client, trip_a, _id_at(sessions, trip_a, "89.90"), "booked", _csrf(client, trip_a))
    _post(client, trip_b, _id_at(sessions, trip_b, "79.90"), "booked", _csrf(client, trip_b))
    _post(client, trip_c, _id_at(sessions, trip_c, "69.90"), "booked", _csrf(client, trip_c))

    html = client.get("/upcoming").text
    assert html.index("Trip B") < html.index("Trip A")
    assert "Trip C" not in html and "ICE 123" not in html

    b_part = html[html.index("Trip B"):html.index("Trip A")]
    a_part = html[html.index("Trip A"):]
    assert "ICE 77" in b_part and "IC 9" in b_part and "07:34" in b_part and "15:26" in b_part
    assert "ICE 105" in a_part and "IC 61" in a_part and "07:34" in a_part and "15:26" in a_part

    for trip_id, price in ((trip_b, "79.90"), (trip_a, "89.90")):
        it_id = _id_at(sessions, trip_id, price)
        assert f'href="/trips/{trip_id}/itineraries/{it_id}/calendar.ics" download' in html
