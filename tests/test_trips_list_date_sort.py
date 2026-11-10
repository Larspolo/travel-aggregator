"""The default order of the trips list by the date of the trip (`sort=date`, the default) (#1984)."""

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import make_password_hash
from app.main import app
from app.models import Trip

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    with Session(sessions.kw["bind"]) as s:
        s.add_all([
            Trip(title="Late trip", origin_text="Utrecht", destination_text="Oslo", date_from=date(2027, 3, 1)),
            Trip(title="Undated trip", origin_text="Utrecht", destination_text="Bern"),
            Trip(title="Early trip", origin_text="Utrecht", destination_text="Zürich", date_from=date(2026, 12, 1)),
        ])
        s.commit()
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    cl = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', cl.get("/login").text).group(1)
    cl.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return cl


def _order(html: str) -> list[str]:
    return re.findall(r">(\w+ trip)</a></h2>", html)


def test_sort_by_date_puts_the_earliest_first_and_no_date_last(client):
    assert _order(client.get("/", params={"sort": "date"}).text) == ["Early trip", "Late trip", "Undated trip"]


def test_default_order_is_the_date_order(client):
    assert _order(client.get("/").text) == ["Early trip", "Late trip", "Undated trip"]
