"""The card "Best offers by source" of the captures page (#1941): one line for each source of `source_wins()`."""
from tests.test_source_wins import _ingest, _trip
from tests.test_trip_page import offer, trip  # noqa: F401  (trip is a fixture)


def test_the_card_shows_the_wins_of_each_source_high_first(trip, sessions):  # noqa: F811
    client, auth, t1 = trip
    trips = [t1] + [_trip(sessions) for _ in range(4)]
    for i, t in enumerate(trips):  # bahn.de in 5 trips, best in 3; Trainline in 4 trips, best in 2
        _ingest(client, auth, t, "bahn.de", [offer("80.00" if i < 3 else "95.00")])
        if i:
            _ingest(client, auth, t, "thetrainline.com", [offer("90.00" if i < 3 else "85.00", "ICE 9")])
    page = client.get("/captures").text
    assert 'id="source-wins"' in page
    bahn = page.index("bahn.de: best in 3 of 5 trips (last 12 months)")
    assert page.index("Trainline: best in 2 of 4 trips (last 12 months)") > bahn


def test_no_card_with_no_capture_or_with_failed(trip, sessions):  # noqa: F811
    client, auth, t1 = trip
    assert 'id="source-wins"' not in client.get("/captures").text
    _ingest(client, auth, t1, "bahn.de", [offer("80.00")])
    assert 'id="source-wins"' in client.get("/captures").text
    assert 'id="source-wins"' not in client.get("/captures?failed=1").text
    assert 'id="source-wins"' not in client.get("/captures?source=bahn.de").text
