"""The info texts of the compartment of an ÖBB Nightjet fare (#2787): the parser gives the English texts of the
cheapest compartment (at most 8 of 200 characters), the ingest stores them one per line, the trip page lists them
escaped, the export and import keep them, and the migration upgrades and downgrades."""

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import inspect, select

from app.ingest import upsert_offers
from app.models import Fare, Trip
from app.parsers.oebb import OebbParser, _infotexts
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export
from tests.test_fare_reservations import reserved
from tests.test_self_transfer import post
from tests.test_trip_import import _fare, _itinerary
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

FIX = Path(__file__).parent / "fixtures" / "oebbtickets.at" / "fares-amsterdam-wien-nightjet.json"
T1 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
T2 = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)
SLEEPER_TEXTS = [
    "Other travellers in the compartment possible",
    "Breakfast à la carte included",
    "With private bathroom (WC / shower facilities)",
    "Covered bed incl. blanket and pillow",
    "Lockable compartment",
    "With WIFI and modern design",
]


def load():
    return json.loads(FIX.read_text(encoding="utf-8"))


def test_the_sleeper_fare_has_the_info_texts_of_its_compartment():
    r = OebbParser().parse(load())
    assert r.errors == []
    assert [o.compartment_info for o in r.offers if o.fare_name == "Sleeper"] == [SLEEPER_TEXTS]
    assert [o.compartment_info for o in r.offers if o.fare_name == "Seat"] == [
        ["2nd class in an open-plan car", "Priority seat for passengers with disabilities",
         "With WIFI and modern design"],
    ]


def test_no_info_texts_give_no_list_and_a_script_stays_text():
    assert _infotexts({}) == []
    assert _infotexts({"infotexts": None}) == []
    assert _infotexts({"infotexts": [{"en": "  "}, {"de": "nur deutsch"}, "x"]}) == []
    assert _infotexts({"infotexts": [{"en": "  <script>alert(1)</script>  "}]}) == ["<script>alert(1)</script>"]
    raw = load()
    raw["offerSections"][0].pop("media")
    assert all(o.compartment_info is None for o in OebbParser().parse(raw).offers)


def test_at_most_8_texts_of_200_characters_are_stored():
    texts = [{"en": f"text {i}"} for i in range(9)]
    assert _infotexts({"infotexts": texts}) == [f"text {i}" for i in range(8)]
    long = _infotexts({"infotexts": [{"en": "a" * 300}]})
    assert long == ["a" * 200]
    assert _infotexts({"infotexts": [{"en": "line one\nline two"}]}) == ["line one line two"]


def test_the_trip_page_lists_the_texts_escaped(trip):  # noqa: F811
    client, auth, trip_id = trip
    offer = reserved(None, None)
    offer["fare_name"] = "Sleeper"
    offer["compartment_info"] = ["Lockable compartment", "<script>alert(1)</script>"]
    assert post(client, auth, trip_id, [offer])["created"] == 1
    page = client.get(f"/trips/{trip_id}").text
    assert "<li>Lockable compartment</li>" in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page and "<script>alert(1)" not in page


def test_a_second_capture_updates_the_stored_texts(sessions):
    with sessions() as s:
        t = Trip(title="texts")
        s.add(t)
        s.commit()
        trip_id = t.id
        upsert_offers(s, trip_id, None, OebbParser().parse(load()).offers, source="oebbtickets.at", captured_at=T1)
        s.commit()
    raw = load()
    for offer in raw["offerSections"][0]["travelClasses"][0]["offers"]:
        for c in (offer.get("reservation") or {}).get("compartments") or []:
            if c["id"] == 5000174 and c.get("price") is not None:
                c["price"] = c["price"] - 10
    second = OebbParser().parse(raw).offers
    with sessions() as s:
        upsert_offers(s, trip_id, None, second, source="oebbtickets.at", captured_at=T2)
        s.commit()
        fare = s.scalars(select(Fare).where(Fare.fare_name == "Sleeper")).one()
        assert fare.compartment_info == "\n".join(SLEEPER_TEXTS)


def test_the_export_and_import_keep_the_texts(sessions):
    with sessions() as s:
        t = Trip(title="Texts", origin_text="A", destination_text="B", travelers=1, status="planning")
        it = _itinerary(T1, T2, 60, "NJ 40421")
        fare = _fare("Sleeper", (T1, "204.80"))
        fare.compartment_info = "Lockable compartment\nWith WIFI and modern design"
        it.fares.append(fare)
        plain = _fare("Seat", (T1, "59.80"))
        it.fares.append(plain)
        t.itineraries.append(it)
        s.add(t)
        s.commit()
        export = trip_export(load_trip(s, t.id))
    fares = {f["fare_name"]: f for f in export["itineraries"][0]["fares"]}
    assert fares["Sleeper"]["compartment_info"] == ["Lockable compartment", "With WIFI and modern design"]
    assert fares["Seat"]["compartment_info"] is None
    export["title"] = "Texts copy"
    with sessions() as s:
        trip_id = import_trip(s, export).trip_id
        s.commit()
        again = trip_export(load_trip(s, trip_id))
    kept = {f["fare_name"]: f for f in again["itineraries"][0]["fares"]}
    assert kept["Sleeper"]["compartment_info"] == ["Lockable compartment", "With WIFI and modern design"]
    assert kept["Seat"]["compartment_info"] is None


def test_the_migration_upgrades_and_downgrades_to_0077(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0078")
    engine = create_engine(empty_database_url)
    try:
        assert "compartment_info" in {c["name"] for c in inspect(engine).get_columns("fares")}
        command.downgrade(cfg, "0077")
        assert "compartment_info" not in {c["name"] for c in inspect(engine).get_columns("fares")}
        command.upgrade(cfg, "head")
        assert "compartment_info" in {c["name"] for c in inspect(engine).get_columns("fares")}
    finally:
        engine.dispose()
