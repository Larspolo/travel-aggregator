"""Pin, Hide and Booked are small icon buttons in the last cell of a row (#591)."""

import re

from app.models import Itinerary
from tests.test_trip_hide import csrf, trip  # noqa: F401


def _row(html):
    return html[html.index('<tbody id="rows">'):].split("</tr>", 1)[0]


def test_the_actions_are_the_last_cell_with_labels_and_post_forms(trip, sessions):  # noqa: F811
    client, trip_id = trip
    row = _row(client.get(f"/trips/{trip_id}").text)
    cells = re.findall(r"<td[ >]", row)
    last = row[row.rindex("<td"):]
    assert 'class="actions"' in last and len(cells) == 5
    for label in ["Pin", "Hide", "Mark as booked"]:
        assert f'aria-label="{label}" title="{label}"' in last
    assert last.count('<form method="post"') == 3 and last.count('name="csrf_token"') == 3
    with sessions() as s:
        it_id = s.query(Itinerary).filter_by(trip_id=trip_id).first().id
    for action in ["pin", "hide", "booked"]:
        r = client.post(f"/trips/{trip_id}/itineraries/{it_id}/{action}",
                        data={"csrf_token": csrf(client, trip_id)}, follow_redirects=False)
        assert r.status_code == 303, action
    with sessions() as s:
        it = s.get(Itinerary, it_id)
        assert (it.pinned, it.hidden, it.booked) == (True, True, True)
    html = client.get(f"/trips/{trip_id}?show_hidden=1").text
    for label in ["Unpin", "Unhide", "Not booked"]:
        assert f'aria-label="{label}"' in html
