"""The whole manual entry feature: an offer from the form ranks like a captured offer (#120)."""

from sqlalchemy import func, select

from app import tokens
from app.models import Capture, FarePrice, Itinerary, Trip
from tests.test_manual_entry import _form, _token, client  # noqa: F401  (client is a fixture)
from tests.test_trip_page import ingest, offer


def _count(sessions, model):
    with sessions() as s:
        return s.scalar(select(func.count()).select_from(model))


def test_a_manual_offer_ranks_like_a_captured_offer(sessions, client):  # noqa: F811
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Berlin", travelers=1)
        s.add(trip)
        s.commit()
        trip_id = trip.id
    ingest(client, {"Authorization": f"Bearer {token}"}, trip_id, [offer("89.90")])
    path = f"/trips/{trip_id}/offers/new"
    for _ in range(2):
        r = client.post(path, data=_form(csrf_token=_token(client, path)), follow_redirects=False)
        assert r.status_code == 303
    page = client.get(f"/trips/{trip_id}").text
    # captured: 89.90 + 472 min × 15/60 = 118 + 1 transfer × 10; manual: 49.90 + 390 min × 15/60 = 97.50 + 10
    assert "€89.90 price + €118 time + €10 transfers = €217.90" in page
    assert "€49.90 price + €97.50 time + €10 transfers = €157.40" in page
    assert page.index("= €157.40") < page.index("= €217.90")
    # as for the API: the same offer twice is one itinerary, one price row (unchanged) and two captures
    assert (_count(sessions, Itinerary), _count(sessions, FarePrice), _count(sessions, Capture)) == (2, 2, 3)
