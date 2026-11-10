"""The metrics token and GET /metrics (#1892)."""

import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.main import app
from app.models import Trip
from tests.test_upcoming_page import SOON, add, client  # noqa: F401  (client is a fixture)


def _csrf(c) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get("/settings").text).group(1)


def _new_token(c) -> str:
    r = c.post("/settings/metrics-token", data={"csrf_token": _csrf(c)})
    return re.search(r'value="([^"]+)" aria-label="Metrics token"', r.text).group(1)


def _get(token):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return TestClient(app).get("/metrics", headers=headers)


def test_metrics_count_trips_and_itineraries(client, sessions):  # noqa: F811
    with sessions() as s:
        add(s, "One", SOON)
        add(s, "Two", SOON + timedelta(days=1))
        trip = s.get(Trip, add(s, "Three", SOON)[0])
        trip.itineraries[0].trip = s.get(Trip, add(s, "Four", SOON)[0])
        s.delete(trip)
        s.commit()
        trip = s.query(Trip).filter_by(title="One").one()
        trip.status = "archived"
        s.commit()
    r = _get(_new_token(client))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain; version=0.0.4")
    lines = r.text.splitlines()
    assert "travel_trips 3" in lines and "travel_offers 4" in lines
    assert "# TYPE travel_trips gauge" in lines and any(x.startswith("# HELP travel_offers ") for x in lines)


def test_two_trips_and_three_itineraries(client, sessions):  # noqa: F811
    with sessions() as s:
        add(s, "A", SOON)
        trip = s.get(Trip, add(s, "B", SOON)[0])
        other = s.query(Trip).filter_by(title="A").one()
        extra = s.get(Trip, add(s, "C", SOON)[0])
        extra.itineraries[0].trip = other
        s.flush()
        s.delete(extra)
        s.commit()
        assert trip is not None
    lines = _get(_new_token(client)).text.splitlines()
    assert "travel_trips 2" in lines and "travel_offers 3" in lines


def test_bad_tokens_get_401(client, sessions):  # noqa: F811
    with sessions() as s:
        api = tokens.create(s, "ingest")
        s.commit()
    for token in (None, "wrong", api):
        r = _get(token)
        assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    old = _new_token(client)
    assert "Stop the token" in client.get("/settings").text
    new = _new_token(client)
    assert _get(old).status_code == 401 and _get(new).status_code == 200
    r = client.post("/settings/metrics-token/revoke", data={"csrf_token": _csrf(client)})
    assert "No metrics token." in r.text
    r = _get(new)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_the_token_shows_once(client):  # noqa: F811
    token = _new_token(client)
    page = client.get("/settings").text
    assert token not in page and "A metrics token is active." in page


@pytest.mark.parametrize("path", ["/settings/metrics-token", "/settings/metrics-token/revoke"])
def test_the_forms_need_the_login_and_the_csrf_token(client, path):  # noqa: F811
    assert client.post(path, data={"csrf_token": "bad"}, follow_redirects=False).status_code in (400, 403)
    anon = TestClient(app)
    assert anon.post(path, data={"csrf_token": "x"}, follow_redirects=False).status_code in (303, 401, 403)
    assert "No metrics token." in client.get("/settings").text
