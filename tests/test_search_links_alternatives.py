"""Search links of the alternative places of a trip (#1424)."""

from datetime import date
from types import SimpleNamespace

from app import search_links
from app.search_links import links_for_trip, search_link

TEMPLATE = "https://example.test/s?f={from}&t={to}&d={date}"
SOURCES = {
    "bahn": {
        "source": "bahn.de",
        "name": "bahn.de",
        "template": TEMPLATE,
        "date_format": "%Y-%m-%d",
        "places": {"Amsterdam": "Amsterdam Centraal", "Zürich": "Zürich HB", "Basel": "Basel SBB"},
    }
}


def _trip(origin, destination, origin_alt=None, destination_alt=None):
    return SimpleNamespace(
        origin_text=origin,
        destination_text=destination,
        origin_alt_text=origin_alt,
        destination_alt_text=destination_alt,
        date_from=date(2026, 12, 24),
    )


def _use_sources(monkeypatch):
    monkeypatch.setattr(search_links, "load_sources", lambda: SOURCES)


def test_alternative_destination_gives_extra_link_named_by_pair(monkeypatch):
    _use_sources(monkeypatch)

    links = links_for_trip(_trip("Amsterdam", "Zürich", destination_alt="Basel"))

    assert [name for name, _ in links] == ["bahn.de", "bahn.de: Amsterdam → Basel"]
    main = search_link(TEMPLATE, SimpleNamespace(origin_text="Amsterdam Centraal", destination_text="Zürich HB", date_from=date(2026, 12, 24)))
    assert links[0][1] == main
    assert "Basel%20SBB" in links[1][1]
    assert "Zürich%20HB" not in links[1][1]


def test_trip_without_alternative_gives_only_main_link(monkeypatch):
    _use_sources(monkeypatch)

    links = links_for_trip(_trip("Amsterdam", "Zürich"))

    assert [name for name, _ in links] == ["bahn.de"]


def test_alternative_origin_and_destination_give_every_other_pair(monkeypatch):
    _use_sources(monkeypatch)

    links = links_for_trip(_trip("Amsterdam", "Zürich", origin_alt="Basel", destination_alt="Basel"))

    assert [name for name, _ in links] == [
        "bahn.de",
        "bahn.de: Amsterdam → Basel",
        "bahn.de: Basel → Zürich",
        "bahn.de: Basel → Basel",
    ]


def test_pair_without_place_value_gives_no_extra_link(monkeypatch):
    _use_sources(monkeypatch)

    links = links_for_trip(_trip("Amsterdam", "Zürich", destination_alt="Utrecht"))

    assert [name for name, _ in links] == ["bahn.de"]
