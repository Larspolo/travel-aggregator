"""The bad share links per address (#904): 20 bad links lock that address for 15 minutes with 429 and Retry-After."""

import pytest
from fastapi.testclient import TestClient

from app.auth import token_limiter
from app.main import app
from tests.test_share import share
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    token_limiter.reset()
    c = Clock()
    monkeypatch.setattr(token_limiter, "clock", c)
    yield c
    token_limiter.reset()


def test_twenty_bad_links_lock_the_address_for_15_minutes(trip, clock):  # noqa: F811
    client, _, trip_id = trip
    link = share(client, trip_id)
    bad = TestClient(app, client=("198.51.100.7", 50000))
    for i in range(token_limiter.ADDRESS_MAX):
        assert bad.get(f"/s/unknown-{i}").status_code == 404
    r = bad.get(link)  # the 21st request, with a good link
    assert r.status_code == 429
    assert r.headers["retry-after"] == str(token_limiter.LOCK) == "900"
    assert r.headers["cache-control"] == "no-store"
    assert bad.get("/s/unknown-x").status_code == 429
    other = TestClient(app, client=("203.0.113.9", 50000))
    assert other.get(link).status_code == 200
    clock.now += token_limiter.LOCK
    assert bad.get(link).status_code == 200
