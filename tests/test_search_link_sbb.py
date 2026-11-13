from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote, urlsplit

from app.search_links import links_for_trip


def _trip(origin, destination, date_from):
    return SimpleNamespace(origin_text=origin, destination_text=destination, date_from=date_from,
                           origin_alt_text=None, destination_alt_text=None)


def _sbb_link(trip):
    links = dict(links_for_trip(trip))
    return links["SBB"]


def test_basel_to_zurich_gives_sbb_search_link_with_date_and_places():
    link = _sbb_link(_trip("Basel", "Zürich", date(2026, 12, 1)))

    parts = urlsplit(link)
    assert parts.scheme == "https"
    assert parts.netloc == "www.sbb.ch"
    assert parts.path == "/en"
    query = parse_qs(parts.query)
    assert query["stops"] == ["Basel SBB_I8500010~Zürich HB_I8503000"]
    assert query["day"] == ["2026-12-01"]
    assert query["moment"] == ["dep"]


def test_sbb_link_encodes_the_places_of_the_trip():
    link = _sbb_link(_trip("Basel", "Zürich", date(2026, 12, 1)))

    assert "Zürich" not in link
    assert "%C3%BC" in link
    assert unquote(link).count("~") == 1


def test_sbb_link_has_the_same_places_in_the_other_direction():
    link = _sbb_link(_trip("Zürich", "Basel", date(2026, 12, 1)))

    query = parse_qs(urlsplit(link).query)
    assert query["stops"] == ["Zürich HB_I8503000~Basel SBB_I8500010"]


def test_sbb_link_is_absent_for_a_place_without_sbb_value():
    links = dict(links_for_trip(_trip("Basel", "Berlin", date(2026, 12, 1))))

    assert "SBB" not in links
