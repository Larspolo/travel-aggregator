"""The select, date and time controls look like the text inputs in light and dark mode (#667)."""

import os

import pytest

from tests.test_mobile_whole import DESKTOP, PHONE, _launch, live  # noqa: F401  (live is a fixture)
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

pytestmark = pytest.mark.slow

LOOK = """() => {
  const muted = getComputedStyle(document.documentElement).getPropertyValue('--muted').trim();
  const probe = document.createElement('div'); probe.style.color = muted; document.body.append(probe);
  const mutedRgb = getComputedStyle(probe).color; probe.remove();
  const text = document.querySelector('input[type=text], input:not([type])');
  const t = getComputedStyle(text);
  const icon = [...document.styleSheets].flatMap(sh => [...sh.cssRules]).some(r =>
    (r.selectorText || '').includes('input[type="time"]::-webkit-calendar-picker-indicator')
    && r.style.background.includes('var(--muted)'));
  const out = [];
  for (const el of document.querySelectorAll('select, input[type=date], input[type=time]')) {
    if (!el.offsetParent) continue;
    const s = getComputedStyle(el);
    const r = {tag: el.tagName + (el.type ? ':' + el.type : ''), appearance: s.appearance,
      same: s.minHeight === t.minHeight && s.borderTopWidth === t.borderTopWidth && s.borderRadius === t.borderRadius
        && s.borderTopColor === t.borderTopColor};
    if (el.tagName === 'SELECT') r.arrow = s.backgroundImage.includes(mutedRgb);
    else r.icon = icon;  // computed style of this pseudo element is not readable: check the rule
    out.push(r);
  }
  return out;
}"""


def test_the_controls_follow_the_tokens(live, tmp_path):  # noqa: F811
    from playwright.sync_api import sync_playwright

    base, tid = live
    shots = os.environ.get("SCREENSHOT_DIR", str(tmp_path))
    os.makedirs(shots, exist_ok=True)
    with sync_playwright() as p:
        browser = _launch(p)
        for scheme in ("light", "dark"):
            for width in (DESKTOP, PHONE):
                for name, path in (("trips-new", "/trips/new"), ("trip-panel", f"/trips/{tid}")):
                    page = browser.new_page(viewport={"width": width, "height": 800}, color_scheme=scheme,
                                            device_scale_factor=2)
                    page.goto(base + path)
                    page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
                    controls = page.evaluate(LOOK)
                    assert controls, path
                    for c in controls:
                        assert c["same"], (path, scheme, c)
                        assert c.get("arrow", c.get("icon")), (path, scheme, c)
                        if c["tag"] == "SELECT:select-one":
                            assert c["appearance"] == "none", c
                    page.screenshot(path=f"{shots}/{name}-{width}-{scheme}.png", full_page=True)
                    page.close()
        browser.close()
