"""The compartment of an ÖBB Nightjet tier fare (#2786): the parser gives the English name of the cheapest
compartment of each tier, the ingest stores and updates it, the trip page shows it, the export and import keep it,
and the migration upgrades and downgrades."""

import copy
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import inspect, select

from app.ingest import upsert_offers
from app.models import Fare, Trip
from app.parsers.oebb import OebbParser, _tiers
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export
from tests.test_trip_import import _fare, _itinerary
from tests.test_fare_reservations import reserved
from tests.test_self_transfer import post
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

FIX = Path(__file__).parent / "fixtures" / "oebbtickets.at" / "fares-amsterdam-wien-nightjet.json"
T1 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
T2 = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)
SLEEPER = "Comfort ladies only compartment for 2 passengers, including WC (Double)"


def load():
    return json.loads(FIX.read_text(encoding="utf-8"))


def test_each_tier_has_the_compartment_of_its_cheapest_price():
    r = OebbParser().parse(load())
    assert r.errors == []
    assert [(o.fare_name, o.price_amount, o.compartment) for o in r.offers] == [
        ("Seat", Decimal("59.80"), "Priority seat for passengers with disabilities"),
        ("Couchette", Decimal("124.80"), "Comfort compartment for 4 passengers"),
        ("Sleeper", Decimal("204.80"), SLEEPER),
    ]


def test_a_null_price_is_never_the_compartment_and_no_media_gives_none():
    raw = load()
    section = raw["offerSections"][0]
    private = "Comfort private compartment in a couchette coach for up to 4 passengers"
    assert private not in {c for _, _, _, c in _tiers(section).values()}
    bare = copy.deepcopy(raw["offerSections"][1])
    bare.pop("media", None)
    assert _tiers(bare) == {}
    raw["offerSections"][0].pop("media")
    r = OebbParser().parse(raw)
    assert r.errors == [] and [o.compartment for o in r.offers] == [None]


def mini_cabin():
    """A capture whose cheapest couchette is the Mini Cabin (the same price)."""
    raw = load()
    for offer in raw["offerSections"][0]["travelClasses"][0]["offers"]:
        for c in (offer.get("reservation") or {}).get("compartments") or []:
            if c["id"] == 5000127 and c.get("price") is not None:
                c["price"] = c["price"] + 1
    return raw


def test_a_second_capture_updates_the_stored_compartment(sessions):
    with sessions() as s:
        t = Trip(title="nightjet")
        s.add(t)
        s.commit()
        trip_id = t.id
        upsert_offers(s, trip_id, None, OebbParser().parse(load()).offers, source="oebbtickets.at", captured_at=T1)
        s.commit()
        before = s.scalars(select(Fare).where(Fare.fare_name == "Couchette")).one()
        fare_id, prices = before.id, len(before.prices)
        assert before.compartment == "Comfort compartment for 4 passengers"
    second = OebbParser().parse(mini_cabin()).offers
    assert [o.compartment for o in second if o.fare_name == "Couchette"] == ["Mini Cabin"]
    with sessions() as s:
        upsert_offers(s, trip_id, None, second, source="oebbtickets.at", captured_at=T2)
        s.commit()
        after = s.scalars(select(Fare).where(Fare.fare_name == "Couchette")).one()
        assert (after.id, after.compartment) == (fare_id, "Mini Cabin")
        assert len(after.prices) == prices


def test_a_fare_of_another_source_has_no_compartment(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    assert post(client, auth, trip_id, [reserved(None, None)])["created"] == 1
    with sessions() as s:
        assert list(s.scalars(select(Fare.compartment))) == [None]


def test_the_trip_page_shows_the_compartment_escaped(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["fare_name"] = "Sleeper"
    offer["compartment"] = SLEEPER
    other = reserved(None, None)
    other["fare_name"] = "Couchette"
    other["compartment"] = "<b>bold</b>"
    other["legs"][0]["service_no"] = "X 1"
    post(client, auth, trip_id, [offer, other])
    page = client.get(f"/trips/{trip_id}").text
    assert f"Sleeper: {SLEEPER}" in page
    assert "&lt;b&gt;bold&lt;/b&gt;" in page and "<b>bold</b>" not in page


def test_the_export_and_import_keep_the_compartment(sessions):
    with sessions() as s:
        t = Trip(title="Compartment", origin_text="A", destination_text="B", travelers=1, status="planning")
        it = _itinerary(T1, T2, 60, "NJ 40421")
        fare = _fare("Couchette", (T1, "124.80"))
        fare.compartment = "Mini Cabin"
        it.fares.append(fare)
        t.itineraries.append(it)
        s.add(t)
        s.commit()
        export = trip_export(load_trip(s, t.id))
    assert export["itineraries"][0]["fares"][0]["compartment"] == "Mini Cabin"
    export["title"] = "Compartment copy"
    with sessions() as s:
        trip_id = import_trip(s, export).trip_id
        s.commit()
        again = trip_export(load_trip(s, trip_id))
    assert again["itineraries"][0]["fares"][0]["compartment"] == "Mini Cabin"


def test_the_migration_upgrades_and_downgrades_to_0074(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0075")
    engine = create_engine(empty_database_url)
    try:
        assert "compartment" in {c["name"] for c in inspect(engine).get_columns("fares")}
        command.downgrade(cfg, "0074")
        assert "compartment" not in {c["name"] for c in inspect(engine).get_columns("fares")}
        command.upgrade(cfg, "head")
        assert "compartment" in {c["name"] for c in inspect(engine).get_columns("fares")}
    finally:
        engine.dispose()
