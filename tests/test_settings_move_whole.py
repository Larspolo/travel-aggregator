"""The move of the settings and of a trip to an empty database (#1208, epic #1204): the settings and the trip are
exported, the database is emptied, both files are imported, and the trip page ranks the trip as before."""

import copy
import json
import re
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text

from app.models import AccessTime, Base, CurrencyRate, ScoreProfile, Setting, SourceFee, Trip
from app.notify import REMINDER_DAYS_KEY, SOURCE_ALERT_KEY
from app.profiles import to_config
from app.ranking import Weights
from tests.test_ingest_api import BODY
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture: a logged-in client and an empty trip)


def _offer(price, currency, service_no):
    o = copy.deepcopy(BODY["offers"][0])
    o.update(price_amount=price, price_currency=currency, fare_name="Sparpreis")
    o["legs"][0]["service_no"] = service_no
    return o


def _ingest(client, auth, trip_id, source, offers):
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, source=source, offers=offers)
    assert client.post("/api/ingest", json=body, headers=auth).status_code == 200


def _settings(sessions):
    """Two profiles (one default), a place, a rate, a fee and two settings of the file."""
    now = datetime.now(timezone.utc)
    with sessions() as s:
        s.add(ScoreProfile(name="Default", is_default=True, config_json=to_config(Weights())))
        s.add(ScoreProfile(name="Fast", is_default=False, config_json=to_config(Weights(hour_markup=Decimal("50")))))
        s.add(AccessTime(place_text="Amsterdam Centraal", kind="access", minutes=20, cost=Decimal("2.50")))
        s.add(CurrencyRate(code="USD", eur_per_unit=Decimal("0.920000"), updated_at=now))
        s.add(SourceFee(source="ns", amount=Decimal("1.50"), updated_at=now))
        s.add(Setting(key=REMINDER_DAYS_KEY, value="7"))
        s.add(Setting(key=SOURCE_ALERT_KEY, value="1"))
        s.commit()


def _rows(page):
    """The offer rows of the trip page as text, without the ids: the route, the times, the fares and the cost."""
    rows = re.findall(r'<tr id="it-\d+">(.*?)</tr>', page, re.S)
    return [" ".join(re.sub(r"<[^>]+>", " ", row).split()) for row in rows]


def _csrf(client, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def _strip_time(data):
    return {k: v for k, v in data.items() if k != "exported_at"}


def test_the_settings_and_a_trip_move_to_an_empty_database_and_rank_the_same(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _settings(sessions)
    _ingest(client, auth, trip_id, "bahn.de", [_offer("89.90", "EUR", "ICE 105")])
    _ingest(client, auth, trip_id, "ns", [_offer("120.00", "USD", "ICE 123")])
    before = _rows(client.get(f"/trips/{trip_id}").text)
    assert len(before) == 2 and all("€" in row and "no rate" not in row for row in before)
    settings_before = _strip_time(client.get("/settings/export.json").json())
    trip_file = client.get(f"/trips/{trip_id}/export.json").json()

    # the new instance: an empty database
    with sessions() as s:
        s.execute(text(f"TRUNCATE {', '.join(t.name for t in Base.metadata.sorted_tables)} RESTART IDENTITY CASCADE"))
        s.commit()
    with sessions() as s:
        assert s.query(Trip).count() == 0 and s.query(ScoreProfile).count() == 0 and s.query(Setting).count() == 0

    # the imports: the settings first, then the trip as a new trip
    r = client.post("/settings/import", data={"csrf_token": _csrf(client, "/settings/import")},
                    files={"file": ("settings.json", json.dumps(settings_before), "application/json")})
    assert r.status_code == 200 and "imported" in r.text
    r = client.post("/trips/import", data={"csrf_token": _csrf(client, "/trips/import"), "target": ""},
                    files={"file": ("trip.json", json.dumps(trip_file), "application/json")},
                    follow_redirects=False)
    assert r.status_code == 303, r.text
    new_id = int(r.headers["location"].rsplit("/", 1)[1])

    assert _strip_time(client.get("/settings/export.json").json()) == settings_before
    after = _rows(client.get(f"/trips/{new_id}").text)
    assert after == before
