"""The @match lines of flixbus.user.js cover the shop hosts (#533)."""

import re
from fnmatch import fnmatchcase
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "userscripts" / "flixbus.user.js"


def _matches(url: str) -> bool:
    patterns = re.findall(r"^// @match\s+(\S+)", SCRIPT.read_text(), re.M)
    return any(fnmatchcase(url, p) for p in patterns)


def test_shop_and_www_hosts_match():
    for url in (
        "https://shop.flixbus.nl/search?departureCity=x",
        "https://shop.flixbus.com/search",
        "https://shop.flixbus.de/search",
        "https://www.flixbus.nl/",
        "https://www.flixbus.com/en/search",
    ):
        assert _matches(url), url


def test_other_hosts_do_not_match():
    assert not _matches("https://example.com/flixbus.nl/")
