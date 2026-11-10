from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from app.search_links import day_links, links_by_source


def _trip(origin, destination, date_from):
    return SimpleNamespace(origin_text=origin, destination_text=destination, date_from=date_from)


def test_day_link_uses_the_given_day_and_trip_keeps_its_date():
    trip = _trip("Amsterdam", "Berlin", date(2027, 5, 3))

    links = day_links(trip, date(2027, 5, 5))

    bahn = links["bahn.de"][1]
    assert parse_qs(urlsplit(bahn).fragment)["hd"] == ["2027-05-05T00:00:00"]
    assert parse_qs(urlsplit(links_by_source(trip)["bahn.de"][1]).fragment)["hd"] == ["2027-05-03T00:00:00"]
    assert trip.date_from == date(2027, 5, 3)


def test_source_without_template_or_place_gives_none():
    trip = _trip("Amsterdam", "Berlin", date(2027, 5, 3))

    links = day_links(trip, date(2027, 5, 5))

    assert links["sncf-connect.com"][1] is None
    assert day_links(_trip("Atlantis", "Berlin", date(2027, 5, 3)), date(2027, 5, 5))["bahn.de"][1] is None
