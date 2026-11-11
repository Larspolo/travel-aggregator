"""The part rows of the compare view for a train, a bus and a flight from the ingest API (#2088)."""

import copy
import re
from decimal import Decimal

from sqlalchemy import select

from app.models import AccessTime, Itinerary
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

# a transfer shorter than 40 minutes costs €20; 4 night hours cost €15
PARAMS = {"short_transfer_min": "40", "short_transfer_penalty": "20", "night_adjust": "15",
          "airport_before_min": "0", "airport_after_min": "0"}
AMOUNT = re.compile(r"^(−?)€([0-9,]+(?:\.[0-9]+)?)")
COST = re.compile(r'<[a-z]+ class="breakdown">([^<]*)</')


def night_bus(price):
    """A bus 22:00 → 07:00 of the next day: 9 hours, no transfer."""
    o = copy.deepcopy(direct(price))
    o["legs"] = [dict(o["legs"][0], mode="bus", carrier="FlixBus", service_no="N 1",
                      depart_at="2026-12-20T22:00:00+01:00", arrive_at="2026-12-21T07:00:00+01:00")]
    return o


def flight(price):
    """Schiphol 09:00 → Zürich Flughafen 10:00."""
    o = copy.deepcopy(direct(price))
    o["legs"][0].update(mode="flight", carrier="KLM", service_no="KL 1953", from_name="Amsterdam Schiphol",
                        to_name="Zürich Flughafen", arrive_at="2026-12-20T10:00:00+01:00")
    return o


def column_ids(sessions, trip_id):
    with sessions() as s:
        its = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).all()
        by = {i.legs[0].service_no: i.id for i in its}
    return [by["ICE 105"], by["N 1"], by["KL 1953"]]


def setup(client, auth, trip_id, sessions):
    ingest(client, auth, trip_id, [offer("89.90"), night_bus("40.00"), flight("120.00")])
    with sessions() as s:
        s.add_all([AccessTime(place_text="Amsterdam Schiphol", kind="access", minutes=90, cost=Decimal("0")),
                   AccessTime(place_text="Zürich Flughafen", kind="egress", minutes=40, cost=Decimal("6"))])
        s.commit()
    return column_ids(sessions, trip_id)


def part_rows(page):
    """The label and the amount of each cell of each part row (the rows after "Effective cost")."""
    body = page.split('scope="row">Effective cost</th>')[1].split('scope="row">Break-even')[0]
    rows = {}
    for label, cells in re.findall(r'<tr><th scope="row">([^<]*)</th>(.*?)</tr>', body):
        amounts = []
        for cell in re.findall(r"<td[^>]*>(.*?)</td>", cells):
            m = AMOUNT.match(cell)
            assert m, f"no amount in {label}: {cell}"
            amounts.append(Decimal(m.group(2).replace(",", "")) * (-1 if m.group(1) else 1))
        rows[label] = amounts
    return rows


def total(text):
    return Decimal(text.rsplit("€", 1)[1].replace(",", ""))


def test_the_part_cells_add_up_to_the_cost_of_the_trip_table(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ids = setup(client, auth, trip_id, sessions)
    table = client.get(f"/trips/{trip_id}", params=PARAMS).text
    r = client.get(f"/trips/{trip_id}/compare", params={**PARAMS, "it": ids})
    assert r.status_code == 200
    costs = COST.findall(r.text)
    assert len(costs) == 3
    assert all(c in table for c in costs)  # the trip table shows the same breakdowns
    rows = part_rows(r.text)
    assert "access time" in rows and "night travel" in rows and "short transfer" in rows
    for n, cost in enumerate(costs):
        assert sum(cells[n] for cells in rows.values()) == total(cost), (n, cost, rows)
