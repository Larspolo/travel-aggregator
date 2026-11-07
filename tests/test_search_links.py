from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from app.search_links import search_link

TEMPLATE = "https://example.test/s?f={from}&t={to}&d={date}"


def _trip(origin, destination, date_from):
    return SimpleNamespace(origin_text=origin, destination_text=destination, date_from=date_from)


def test_full_trip_encodes_station_and_date():
    link = search_link(TEMPLATE, _trip("Köln Hbf", "Amsterdam Centraal", date(2026, 12, 24)))

    query = parse_qs(urlsplit(link).query)
    assert query["f"] == ["Köln Hbf"]
    assert query["t"] == ["Amsterdam Centraal"]
    assert query["d"] == ["2026-12-24"]
    assert "Köln" not in link
    assert "%20" in link


def test_trip_without_date_gives_start_page():
    link = search_link(TEMPLATE, _trip("Köln Hbf", "Amsterdam Centraal", None))

    assert link == "https://example.test/"


def test_trip_without_origin_gives_start_page():
    link = search_link(TEMPLATE, _trip(None, "Amsterdam Centraal", date(2026, 12, 24)))

    assert link == "https://example.test/"


def test_module_does_not_import_http_client():
    import app.search_links as module

    source = open(module.__file__, encoding="utf-8").read()
    for name in ("requests", "httpx", "urllib.request", "aiohttp", "urllib3"):
        assert f"import {name}" not in source
        assert f"from {name}" not in source
