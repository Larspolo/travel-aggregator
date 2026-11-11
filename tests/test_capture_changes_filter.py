"""The trip page filtered by the changes of a capture: a click on a count of the captures page (#2329)."""

from app.models import Leg, Trip
from tests.test_capture_changes import _berlin_day, _capture, _day
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)


def _setup(sessions, trip_id):
    with sessions() as s:
        caps = [_capture(s, trip_id, n) for n in (1, 2, 3)]
        its = _berlin_day(s, trip_id, *caps)
        for it in its:
            s.add(Leg(itinerary_id=it.id, seq=0, mode="train", from_name="Amsterdam", to_name="Zürich",
                      depart_at=_day(30), depart_offset_min=60, arrive_at=_day(30), arrive_offset_min=60))
        s.commit()
        return caps[1].id, [it.id for it in its]


def test_a_count_opens_the_trip_page_with_only_its_itineraries(sessions, trip):  # noqa: F811
    client, _, trip_id = trip
    cap, (ice105, ice145, ic2021) = _setup(sessions, trip_id)
    captures = client.get(f"/trips/{trip_id}/captures").text
    assert f'href="/trips/{trip_id}?capture={cap}&amp;change=new">1 new</a>' in captures
    page = client.get(f"/trips/{trip_id}?capture={cap}&change=new").text
    assert "Changes of the capture of" in page and "Show all" in page
    assert f"/itineraries/{ic2021}/" in page and f"/itineraries/{ice105}/" not in page
    lower = client.get(f"/trips/{trip_id}?capture={cap}&change=lower").text
    assert f"/itineraries/{ice105}/" in lower and f"/itineraries/{ic2021}/" not in lower
    assert f"capture={cap}&amp;change=lower" in lower  # the sort links keep the filter
    sorted_page = client.get(f"/trips/{trip_id}?capture={cap}&change=lower&sort=price").text
    assert f"/itineraries/{ice145}/" not in sorted_page


def test_another_trip_or_kind_gives_the_full_table(sessions, trip):  # noqa: F811
    client, _, trip_id = trip
    cap, ids = _setup(sessions, trip_id)
    with sessions() as s:
        other = Trip(title="Other", origin_text="A", destination_text="B")
        s.add(other)
        s.commit()
        other_id = other.id
    for url in (f"/trips/{trip_id}?capture={cap}&change=other", f"/trips/{other_id}?capture={cap}&change=new"):
        r = client.get(url)
        assert r.status_code == 200 and "Changes of the capture of" not in r.text
    full = client.get(f"/trips/{trip_id}?capture={cap}&change=other").text
    assert all(f"/itineraries/{i}/" in full for i in ids)
