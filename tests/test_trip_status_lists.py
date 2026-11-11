"""Each status of `TripStatus` shows in the lists that `EXPECTED` names, and in no other list (#496)."""

import typing
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import tokens
from app.main import app
from app.models import Trip
from app.schemas import TripStatus
from tests.test_trips_list import _client

EXPECTED = {"planning": {"/", "api"}, "booked": {"/"}, "archived": {"/?archived=1"}}


def test_expected_names_each_status():
    assert set(EXPECTED) == set(typing.get_args(TripStatus))


@pytest.mark.parametrize("status", typing.get_args(TripStatus))
def test_trip_shows_only_in_its_lists(status, sessions, monkeypatch):
    title = f"Trip-{status}-unique"
    with Session(sessions.kw["bind"]) as s:
        s.add(Trip(title=title, origin_text="A", destination_text="B", date_from=date(2026, 12, 1), status=status))
        s.commit()
    c = _client(monkeypatch)
    for path in ("/", "/?archived=1"):
        assert (title in c.get(path).text) == (path in EXPECTED[status]), path
    with sessions() as s:
        token = tokens.create(s, "test")
    r = TestClient(app).get("/api/trips?status=planning", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert (title in [t["title"] for t in r.json()]) == ("api" in EXPECTED[status])
