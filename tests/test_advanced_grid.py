"""The open "Advanced" part of the weights panel is a compact grid: no cut input and no overlap (#668)."""

import os

import pytest

from tests.test_all_pages_look import DESKTOP, PHONE, _launch, _serve
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow

# 1280 px: the height of the open part was 1987 px with one label per line; the grid makes it at least 40 % shorter (#668).
# The limit grows with the inputs at the same density: 1192 px for 25 inputs; the hour tiers (#1014) added 4, the overnight stop (#1256) 2.
MAX_HEIGHT = 1192 * 31 // 25

# The labels that overlap another label of their fieldset, and the inputs that are wider than their label.
LAYOUT = """() => {
  const adv = document.querySelector('details.advanced');
  adv.open = true;
  const bad = [];
  for (const fs of adv.querySelectorAll('fieldset')) {
    const labels = [...fs.querySelectorAll(':scope > label')].map(l => [l, l.getBoundingClientRect()]);
    for (const [l, r] of labels) {
      const i = l.querySelector('input, select');
      if (i) {
        const ir = i.getBoundingClientRect();
        if (ir.right > r.right + 0.5 || ir.left < r.left - 0.5) bad.push('cut ' + i.name);
      }
      for (const [m, q] of labels) {
        if (m !== l && r.left < q.right - 0.5 && q.left < r.right - 0.5 && r.top < q.bottom - 0.5 && q.top < r.bottom - 0.5)
          bad.push('overlap ' + l.textContent.trim().slice(0, 30));
      }
    }
  }
  return [Math.round(adv.getBoundingClientRect().height), bad];
}"""


def test_advanced_part_is_a_compact_grid(trip, tmp_path):  # noqa: F811
    from playwright.sync_api import sync_playwright

    client, auth, tid = trip
    ingest(client, auth, tid, [offer("89.90")])  # the panel shows only with offers
    shots = os.environ.get("SCREENSHOT_DIR", str(tmp_path))
    os.makedirs(shots, exist_ok=True)
    server, thread, base = _serve()
    heights = {}
    try:
        with sync_playwright() as p:
            browser = _launch(p)
            for width in (DESKTOP, PHONE):
                page = browser.new_page(viewport={"width": width, "height": 844})
                page.goto(f"{base}/trips/{tid}")
                if width == PHONE:
                    page.evaluate("document.querySelector('.panel-toggle').open = true")
                height, bad = page.evaluate(LAYOUT)
                assert bad == [], (width, bad)
                heights[width] = height
                page.locator("details.advanced").screenshot(path=os.path.join(shots, f"advanced-{width}.png"))
                page.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
    print(heights)
    assert heights[DESKTOP] <= MAX_HEIGHT, heights
