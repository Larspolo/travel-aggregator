"""The "Open the trip" link follows a change of the server URL in the panel (#2364). Playwright stubs
GM_xmlhttpRequest, so no request goes to a server or a travel site (P1). No browser dialog is used (P6): the panel
form asks for the URL."""

import pytest

from tests import test_userscript_trip_link as trip_link

pytestmark = pytest.mark.slow
link = trip_link.link
open_page = trip_link.open_page  # the fixture of the trip-link tests


def save_server(pg, value):
    pg.evaluate("""() => { const root = document.getElementById('ta-core-panel').shadowRoot;
        root.querySelector('.set-server').click(); }""")
    pg.wait_for_function("() => !document.getElementById('ta-core-panel').shadowRoot"
                         ".querySelector('.ask').hidden")
    pg.evaluate("""(v) => { const root = document.getElementById('ta-core-panel').shadowRoot;
        root.querySelector('.ask-input').value = v;
        root.querySelector('.ask-save').click(); }""", value)


def test_saving_a_new_server_url_changes_the_link(open_page):
    pg = open_page({"server": "https://travel.example", "trip": 12})
    assert link(pg)["href"] == "https://travel.example/trips/12"
    save_server(pg, "https://other.example/")
    pg.wait_for_function("() => document.getElementById('ta-core-panel').shadowRoot"
                         ".querySelector('.open-trip').getAttribute('href') === 'https://other.example/trips/12'")
    assert link(pg) == {"hidden": False, "href": "https://other.example/trips/12",
                        "target": "_blank", "rel": "noopener"}


def test_saving_an_empty_server_url_hides_the_link(open_page):
    pg = open_page({"server": "https://travel.example", "trip": 12})
    save_server(pg, "")
    pg.wait_for_function("() => document.getElementById('ta-core-panel').shadowRoot"
                         ".querySelector('.open-trip').hidden === true")
    assert link(pg) == {"hidden": True, "href": None, "target": "_blank", "rel": "noopener"}
