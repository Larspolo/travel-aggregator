"""The Flixbus userscript runs on each Flixbus country site (#935): the owner searched on shop.flixbus.co.uk and saw no
panel, because the script had only the .nl, .com and .de sites. All sites send the search to global.api.flixbus.com,
so only the @match lines matter. The bundle and the capture script take their sites from these lines."""

import re
import sys
from pathlib import Path

import app.web.userscripts as userscripts

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import capture  # noqa: E402

FLIXBUS = ROOT / "userscripts" / "flixbus.user.js"
NEEDED = ["nl", "com", "de", "co.uk", "fr", "it", "es", "be", "at", "ch", "pl", "cz", "dk", "se", "pt"]
MATCH = re.compile(r"^// @match[ \t]+(\S+)[ \t]*$", re.MULTILINE)


def matches(text):
    return MATCH.findall(text.split("// ==/UserScript==")[0])


def test_the_flixbus_userscript_runs_on_each_country_site():
    lines = matches(FLIXBUS.read_text("utf-8"))
    assert [f"https://*.flixbus.{tld}/*" for tld in NEEDED if f"https://*.flixbus.{tld}/*" not in lines] == []
    assert all(re.fullmatch(r"https://\*\.flixbus\.[a-z]{2,3}(\.[a-z]{2})?/\*", m) for m in lines)
    assert len(lines) == len(set(lines))


def test_the_bundle_and_the_capture_script_have_the_new_sites():
    bundle = userscripts.bundle("https://ta.example")
    assert "https://*.flixbus.co.uk/*" in matches(bundle)
    assert "https://*.flixbus.co.uk/*" in capture.capture_sites()
    assert "https://*.flixbus.co.uk/*" in matches(capture.USERSCRIPT_FILE.read_text("utf-8"))


def test_the_site_part_of_the_bundle_runs_on_shop_flixbus_co_uk():
    pattern = userscripts.match_regex("https://*.flixbus.co.uk/*")
    assert re.search(pattern, "https://shop.flixbus.co.uk/search?rideDate=24.11.2026&adult=1")
