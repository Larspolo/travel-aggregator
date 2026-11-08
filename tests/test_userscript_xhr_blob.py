"""The core decodes an XHR response of type blob or arraybuffer, and a Blob request body (#1072): the Eurostar page
gets its search like this, and the capture stayed at "ready". Playwright serves all URLs (P1)."""

import json

import pytest

from tests.test_userscript_eurostar import JOURNEYS, REQUEST_BODY, SEARCH_URL, page, status  # noqa: F401

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("rtype", ["blob", "arraybuffer", "json"])
@pytest.mark.parametrize("blob_body", [False, True])
def test_xhr_blob_response_is_captured(page, rtype, blob_body):  # noqa: F811
    page.evaluate("""([u, b, t, bb]) => new Promise(ok => { const x = new XMLHttpRequest();
      x.open('POST', u); x.responseType = t; x.setRequestHeader('content-type', 'application/json');
      x.onload = () => ok(x.status); x.send(bb ? new Blob([b], {type: 'application/json'}) : b); })""",
                  [SEARCH_URL, json.dumps(REQUEST_BODY), rtype, blob_body])
    page.wait_for_function("window.__ingest.length === 1")
    page.wait_for_function("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel')"
                           ".textContent.includes('sent')")
    assert status(page) == f"Captured {JOURNEYS} offers → sent ✓"
    assert page.evaluate("window.__ingest")[0]["body"]["raw"]["request"]["body"]["operationName"] == "NewBookingSearch"
