"""The access and egress time and cost in the ranking (#98)."""

from decimal import Decimal
from types import SimpleNamespace

from app.door import door_extras
from app.models import AccessTime
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

H = Decimal("15")


def _it(start, end):
    return SimpleNamespace(legs=[SimpleNamespace(from_name=start, to_name="x"),
                                 SimpleNamespace(from_name="x", to_name=end)])


def _p(id, text, kind, minutes, cost):
    return SimpleNamespace(id=id, place_text=text, kind=kind, minutes=minutes, cost=Decimal(cost))


def test_egress_match_with_case_and_space():
    extras = door_extras(_it("A", "Zürich Flughafen"), [_p(1, "  zürich flughafen ", "egress", 15, "4.50")], H)
    assert extras == (("egress time", Decimal("3.75")), ("egress cost", Decimal("4.50")))


def test_no_match_and_wrong_kind_add_nothing():
    # no time or cost is added; each kind with places but no match shows a €0 line (#2052)
    assert door_extras(_it("A", "B"), [_p(1, "B", "access", 10, "1"), _p(2, "C", "egress", 10, "1")], H) == (
        ("no access place for A", Decimal(0)), ("no egress place for B", Decimal(0)))


def test_access_and_egress_together_first_by_id():
    places = [_p(3, "A", "access", 60, "9"), _p(1, "a", "access", 20, "0"), _p(2, "B", "egress", 4, "2")]
    assert door_extras(_it("A", "B"), places, H) == (
        ("access time", Decimal("5")), ("access cost", Decimal("0")),
        ("egress time", Decimal("1")), ("egress cost", Decimal("2")))


def test_page_shows_access_and_ranks_lower(sessions, trip):  # noqa: F811
    client, auth, trip_id = trip
    other = direct("150.00")
    other["legs"][0]["from_name"] = "Amsterdam Zuid"
    ingest(client, auth, trip_id, [offer("89.90"), other])
    before = client.get(f"/trips/{trip_id}").text
    assert before.index("= €210") < before.index("= €217.90") and "access" not in before
    with sessions() as s:
        s.add(AccessTime(place_text="amsterdam zuid ", kind="access", minutes=240, cost=Decimal("20")))
        s.commit()
    page = client.get(f"/trips/{trip_id}").text
    assert "€60 access time + €20 access cost" in page
    assert page.index("= €217.90") < page.index("= €290")  # 210 + 60 + 20: now the direct one is second
