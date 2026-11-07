"""The journey box and the price drops of the trip page use the one money format, '€80.90' (#639)."""

import re

from tests.test_price_drops import _pin, _token
from tests.test_reparse import setup  # noqa: F401  (fixture: logged-in client)
from tests.test_trip_journey import _late, _return
from tests.test_trip_page import ingest, offer


def test_a_linked_return_and_a_price_drop_show_no_eur_prefix(setup, sessions):  # noqa: F811
    c, auth, trip_id = setup
    ret = _return(c, sessions, trip_id)
    ingest(c, auth, trip_id, [offer("89.90", "ICE 105")])
    ingest(c, auth, ret, [_late("50.00", "ICE 900")])
    _pin(c, sessions, trip_id, "ICE 105", _token(c, trip_id))
    c.get(f"/trips/{trip_id}")  # the view stores the seen price
    ingest(c, auth, trip_id, [offer("79.90", "ICE 105")])

    page = c.get(f"/trips/{trip_id}").text
    assert "EUR " not in page
    assert "price dropped €10.00" in page and "now €79.90" in page
    assert "€50.00" in page  # the other direction, in the journey box
    assert re.search(r"Total effective cost €\d+\.\d{2}", page)

    page = c.get(f"/trips/{ret}").text
    assert "EUR " not in page
    assert "€50.00" in page and "Total effective cost €" in page
