"""The carrier markup and the excluded-carrier filter use one name per carrier (#2249)."""

import copy
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights
from app.risk import carrier_extras
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def _it(*carriers):
    return SimpleNamespace(legs=[SimpleNamespace(carrier=c) for c in carriers])


def test_one_markup_applies_to_all_source_names_of_a_carrier():
    w = Weights(carrier1_name="Deutsche Bahn", carrier1_markup=Decimal("10"))
    part = (("carrier Deutsche Bahn", Decimal("10")),)
    assert carrier_extras(_it("DB Fernverkehr AG"), w) == part
    assert carrier_extras(_it("Deutsche Bahn"), w) == part
    assert carrier_extras(_it("DB Fernverkehr AG", "Deutsche Bahn"), w) == part


def test_a_raw_part_name_still_matches_only_its_legs():
    w = Weights(carrier1_name="OUIGO", carrier1_markup=Decimal("5"))
    assert carrier_extras(_it("OUIGO"), w) == (("carrier OUIGO", Decimal("5")),)
    assert carrier_extras(_it("TGV INOUI"), w) == ()


def _leg(o, carrier, service):
    o = copy.deepcopy(o)
    o["legs"][0].update(carrier=carrier, service_no=service)
    return o


def test_the_breakdown_shows_the_markup_for_both_sources(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_leg(direct("150.00"), "DB Fernverkehr AG", "ICE 1"),
                                   _leg(direct("140.00"), "Deutsche Bahn", "ICE 2")])
    page = client.get(f"/trips/{trip_id}?carrier1_name=Deutsche+Bahn&carrier1_markup=10").text
    assert page.count("€10 carrier Deutsche Bahn") >= 2, page


def test_one_excluded_entry_per_carrier_hides_all_its_rows(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_leg(direct("100.00"), "FlixBus B.V.", "FLX 1"),
                                   _leg(direct("110.00"), "FlixBus Polska sp. z.o.o.", "FLX 2"),
                                   _leg(direct("120.00"), "Nederlandse Spoorwegen, DB Fernverkehr AG", "ICE 3")])
    page = client.get(f"/trips/{trip_id}").text
    assert 'value="Flix"' in page and 'value="FlixBus B.V."' not in page
    page = client.get(f"/trips/{trip_id}?exclude_carrier=Flix").text
    assert "FLX 1" not in page and "FLX 2" not in page and "ICE 3" in page
    for name in ("NS", "Deutsche+Bahn"):
        page = client.get(f"/trips/{trip_id}?exclude_carrier={name}").text
        assert "ICE 3" not in page and "FLX 1" in page
