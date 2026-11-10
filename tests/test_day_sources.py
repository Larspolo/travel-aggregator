"""The sources of the fares per departure day (#2056): `day_sources` in `app/days.py`."""

from types import SimpleNamespace

from app.days import day_sources


def _it(day, sources, hidden=False):
    fares = [SimpleNamespace(source=s) for s in sources]
    return SimpleNamespace(day=day, fares=fares, hidden=hidden)


def _day_of(it):
    return it.day


def test_sources_per_day_sorted():
    itineraries = [
        _it("2027-05-03", ["trainline", "bahn"]),
        _it("2027-05-03", ["bahn"]),
        _it("2027-05-04", ["bahn"]),
    ]
    assert day_sources(itineraries, _day_of) == {
        "2027-05-03": ["bahn", "trainline"],
        "2027-05-04": ["bahn"],
    }


def test_hidden_and_undated_add_nothing():
    itineraries = [
        _it("2027-05-03", ["flixbus"], hidden=True),
        _it(None, ["ryanair"]),
        _it("2027-05-03", ["bahn"]),
    ]
    assert day_sources(itineraries, _day_of) == {"2027-05-03": ["bahn"]}


def test_same_source_on_one_day_once():
    itineraries = [_it("2027-05-03", ["bahn", "bahn"]), _it("2027-05-03", ["bahn"])]
    assert day_sources(itineraries, _day_of) == {"2027-05-03": ["bahn"]}


def test_no_itineraries_gives_empty_dict():
    assert day_sources([], _day_of) == {}
