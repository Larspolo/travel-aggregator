"""The journey total of the trips list is named as a sum of prices, not as an effective cost (#452)."""

from tests.test_trips_list import _client
from tests.test_trips_list_return import _seed, engine  # noqa: F401


def test_the_label_says_price_and_not_effective_cost(engine, monkeypatch):  # noqa: F811
    _seed(engine)
    html = _client(monkeypatch).get("/").text
    assert "Journey price total: EUR 75.50" in html
    assert "Journey total" not in html
    assert "effective cost" not in html.lower()
