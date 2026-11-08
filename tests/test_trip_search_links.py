"""The trip page shows one search link per source with a template (#318): filled with the trip values,
in a new tab, and no link for a source that has no template or no value for a place of the trip."""

import html
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

import app.search_links as search_links
from app.auth import require_login
from app.main import app
from app.models import Trip

LINK = re.compile(r'<a href="([^"]+)" target="_blank" rel="noopener">Search on ([^<]+)</a>')


@pytest.fixture
def trip(sessions):
    """A client with the owner login and a trip Amsterdam → Berlin on 1 Dec 2026."""
    with sessions() as s:
        t = Trip(title="Amsterdam – Berlin", origin_text="Amsterdam", destination_text="Berlin",
                 date_from=date(2026, 12, 1))
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), trip_id
    app.dependency_overrides.pop(require_login, None)


def _links(page: str) -> dict[str, str]:
    return {name: html.unescape(href) for href, name in LINK.findall(page)}


def test_the_trip_page_shows_four_filled_search_links(trip):
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}").text

    assert len(LINK.findall(page)) == 4
    links = _links(page)
    assert set(links) == {"bahn.de", "NS International", "Flixbus", "Trainline"}
    assert "origin=urn%3Atrainline%3Ageneric%3Aloc%3A5894" in links["Trainline"]
    assert "destination=urn%3Atrainline%3Ageneric%3Aloc%3A7630" in links["Trainline"]
    assert "outwardDate=2026-12-01T00%3A00%3A00" in links["Trainline"]
    assert "so=Amsterdam%20Centraal" in links["bahn.de"]
    assert "zo=Berlin%20Hbf" in links["bahn.de"]
    assert "hd=2026-12-01T00%3A00%3A00" in links["bahn.de"]
    assert "/search/NLASC/DEBHF/20261201" in links["NS International"]
    assert "departureCity=40dde3b8-8646-11e6-9066-549f350fcb0c" in links["Flixbus"]
    assert "rideDate=01.12.2026" in links["Flixbus"]


def test_each_search_link_opens_a_new_tab_without_opener(trip):
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}").text

    for tag in re.findall(r"<a [^>]*Search on [^<]*</a>", page):
        assert 'target="_blank"' in tag
        assert 'rel="noopener"' in tag


def test_a_source_without_template_shows_no_link(trip, monkeypatch):
    client, trip_id = trip
    sources = {
        "known": {"name": "Known", "template": "https://example.test/s?f={from}&t={to}&d={date}",
                  "places": {"Amsterdam": "A", "Berlin": "B"}},
        "bare": {"name": "Bare", "places": {"Amsterdam": "A", "Berlin": "B"}},
    }
    monkeypatch.setattr(search_links, "load_sources", lambda: sources)

    page = client.get(f"/trips/{trip_id}").text

    assert set(_links(page)) == {"Known"}


def test_a_place_without_value_gives_no_link_for_that_source(trip, monkeypatch):
    client, trip_id = trip
    sources = {
        "known": {"name": "Known", "template": "https://example.test/s?f={from}&t={to}&d={date}",
                  "places": {"Amsterdam": "A"}},
    }
    monkeypatch.setattr(search_links, "load_sources", lambda: sources)

    page = client.get(f"/trips/{trip_id}").text

    assert _links(page) == {}
