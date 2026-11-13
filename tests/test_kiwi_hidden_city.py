"""The hidden-city or throwaway mark of a kiwi.com fare (#2793): the parser reads `travelHack`, the ingest stores and
updates it, the trip page shows a badge, the export and import keep it, and the migration upgrades and downgrades."""

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import inspect, select

from app.ingest import upsert_offers
from app.models import Fare, Trip
from app.parsers.kiwi import KiwiParser
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export
from tests.test_fare_reservations import reserved
from tests.test_self_transfer import post
from tests.test_trip_import import _fare, _itinerary
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

FIX = Path(__file__).parent / "fixtures" / "kiwi.com" / "search-amsterdam-lisbon.json"
T1 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
T2 = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)


def raw(hidden=False, throwaway=False, drop=False):
    r = json.loads(FIX.read_text(encoding="utf-8"))
    its = r["response"]["data"]["onewayItineraries"]["itineraries"]
    if drop:
        its[0].pop("travelHack")
    else:
        its[0]["travelHack"].update(isTrueHiddenCity=hidden, isThrowawayTicket=throwaway)
    return r


def first_hacks(r):
    result = KiwiParser().parse(r)
    assert result.errors == []
    return result.offers


def test_the_fixture_as_it_is_gives_no_mark():
    assert {o.travel_hack for o in first_hacks(raw())} == {None}
    assert {o.travel_hack for o in first_hacks(raw(drop=True))} == {None}


def test_the_marks_of_the_first_itinerary():
    for kw, mark in (({"hidden": True}, "hidden-city"), ({"throwaway": True}, "throwaway"),
                     ({"hidden": True, "throwaway": True}, "hidden-city")):
        offers = first_hacks(raw(**kw))
        assert offers[0].travel_hack == mark
        assert {o.travel_hack for o in offers if o.legs != offers[0].legs} == {None}


def test_a_second_capture_with_false_clears_the_mark(sessions):
    with sessions() as s:
        t = Trip(title="kiwi")
        s.add(t)
        s.commit()
        trip_id = t.id
        upsert_offers(s, trip_id, None, first_hacks(raw(hidden=True)), source="kiwi.com", captured_at=T1)
        s.commit()
        assert "hidden-city" in set(s.scalars(select(Fare.travel_hack)))
    with sessions() as s:
        upsert_offers(s, trip_id, None, first_hacks(raw()), source="kiwi.com", captured_at=T2)
        s.commit()
        assert set(s.scalars(select(Fare.travel_hack))) == {None}


def test_the_trip_page_shows_the_badges(trip):  # noqa: F811
    client, auth, trip_id = trip
    a = reserved(None, None)
    a["travel_hack"] = "hidden-city"
    b = reserved(None, None)
    b["travel_hack"] = "throwaway"
    b["legs"][0]["service_no"] = "X 1"
    post(client, auth, trip_id, [a, b])
    page = client.get(f"/trips/{trip_id}").text
    assert ('title="The ticket goes on after your stop: no checked bag, and the airline can cancel the rest">'
            "hidden-city ticket</span>") in page
    assert 'title="You do not use a part of this ticket: the airline can cancel the rest">throwaway ticket</span>' in page


def test_the_export_and_import_keep_the_mark(sessions):
    with sessions() as s:
        t = Trip(title="Hack", origin_text="A", destination_text="B", travelers=1, status="planning")
        it = _itinerary(T1, T2, 60, "KL 1")
        fare = _fare("KL", (T1, "99.00"))
        fare.travel_hack = "throwaway"
        it.fares.append(fare)
        t.itineraries.append(it)
        s.add(t)
        s.commit()
        export = trip_export(load_trip(s, t.id))
    assert export["itineraries"][0]["fares"][0]["travel_hack"] == "throwaway"
    export["title"] = "Hack copy"
    with sessions() as s:
        trip_id = import_trip(s, export).trip_id
        s.commit()
        again = trip_export(load_trip(s, trip_id))
    assert again["itineraries"][0]["fares"][0]["travel_hack"] == "throwaway"


def test_the_migration_upgrades_and_downgrades_to_0076(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0077")
    engine = create_engine(empty_database_url)
    try:
        assert "travel_hack" in {c["name"] for c in inspect(engine).get_columns("fares")}
        command.downgrade(cfg, "0076")
        assert "travel_hack" not in {c["name"] for c in inspect(engine).get_columns("fares")}
        command.upgrade(cfg, "head")
        assert "travel_hack" in {c["name"] for c in inspect(engine).get_columns("fares")}
    finally:
        engine.dispose()
