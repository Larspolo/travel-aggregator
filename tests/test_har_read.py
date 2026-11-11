"""A HAR file gives the raw payloads of its search entries, with no header or cookie (#1562)."""

import base64
import json
import re
from pathlib import Path

import pytest

from app.har import HarError, read_har
from app.parsers import get_parser, parser_classes

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
SECRET = "sessionid=SECRET-COOKIE-123"
SCRIPTS = {"bahn.de": "bahn", "nsinternational.com": "ns", "flixbus.com": "flixbus", "kiwi.com": "kiwi",
           "thetrainline.com": "trainline", "sncf-connect.com": "sncf", "eurostar.com": "eurostar",
           "oebbtickets.at": "oebb"}
# a parser that has no userscript yet: its HAR rule is empty until the userscript ticket (#1786)
NO_SCRIPT = {"sbb.ch"}


def fixture(source, name):
    return json.loads((FIX / source / name).read_text())


def entry(url, method="GET", post=None, text="", mime="application/json", encoding=None):
    req = {"method": method, "url": url, "headers": [{"name": "Cookie", "value": SECRET}],
           "cookies": [{"name": "sessionid", "value": SECRET}]}
    if post is not None:
        req["postData"] = {"mimeType": "application/json", "text": json.dumps(post)}
    content = {"mimeType": mime, "text": text}
    if encoding:
        content["encoding"] = encoding
    return {"request": req, "response": {"status": 200, "headers": [{"name": "Set-Cookie", "value": SECRET}],
                                         "cookies": [{"name": "sessionid", "value": SECRET}], "content": content}}


def bahn_entry(name, b64=False):
    raw = fixture("bahn.de", name)
    text = json.dumps(raw["response"])
    if b64:
        return entry(raw["url"], "POST", raw["request"], base64.b64encode(text.encode()).decode(), encoding="base64")
    return entry(raw["url"], "POST", raw["request"], text)


def kiwi_entry():
    raw = fixture("kiwi.com", "search-amsterdam-zurich.json")
    post = {"query": "query X", "variables": {"options": {"currency": "GBP"},
                                              "search": {"passengers": {"adults": 1, "children": 0, "infants": 0}}}}
    url = "https://api.skypicker.com/umbrella/v2/graphql?featureName=SearchOneWayItinerariesQuery"
    return entry(url, "POST", post, json.dumps(raw["response"]))


def har(*entries):
    return {"log": {"version": "1.2", "entries": list(entries)}}


def test_search_entries_give_raw_payloads_with_no_header_or_cookie():
    result = read_har(json.dumps(har(
        bahn_entry("fahrplan-koeln-muenchen.json"), entry("https://www.bahn.de/logo.png", text="iVBOR", mime="image/png"),
        bahn_entry("fahrplan-amsterdam-berlin.json", b64=True), entry("https://www.kiwi.com/app.js", text="var a=1;",
                                                                      mime="text/javascript"),
        kiwi_entry())))
    assert [s for s, _ in result.items] == ["bahn.de", "bahn.de", "kiwi.com"]
    assert result.skipped == []
    assert SECRET not in json.dumps(result.items) and "SECRET" not in json.dumps(result.items)
    assert all(get_parser(s).parse(raw).offers for s, raw in result.items)
    assert result.items[0][1]["request"] == fixture("bahn.de", "fahrplan-koeln-muenchen.json")["request"]
    assert result.items[2][1]["currency"] == "gbp" and "query" not in json.dumps(result.items[2][1])


def test_a_supported_entry_with_no_json_is_skipped_with_a_reason():
    result = read_har(har(entry("https://int.bahn.de/web/api/angebote/fahrplan", "POST", {}, "<html>error</html>",
                                mime="text/html")))
    assert result.items == []
    assert result.skipped[0]["source"] == "bahn.de" and "not JSON" in result.skipped[0]["reason"]


@pytest.mark.parametrize("data", [{}, {"log": {}}, {"log": {"entries": {}}}, [], "not json"])
def test_a_file_with_no_entries_is_an_error(data):
    with pytest.raises(HarError):
        read_har(data if isinstance(data, str) else json.dumps(data))


def consts(js):
    return dict(re.findall(r'const ([A-Z_]+) = "([^"]*)";', js))


@pytest.mark.parametrize("source", list(SCRIPTS))
def test_the_url_rule_of_each_parser_matches_its_userscript(source):
    assert set(SCRIPTS) | NO_SCRIPT == set(parser_classes())
    cls = parser_classes()[source]
    js = (ROOT / "userscripts" / f"{SCRIPTS[source]}.user.js").read_text()
    c = consts(js)
    m = re.search(r"const PATHS = (?:new Set\()?\[([^\]]*)\]", js)
    if m:
        paths = {c.get(x.strip(), x.strip().strip('"')) for x in m.group(1).split(",")}
    else:
        paths = {c["PATH"]}
    assert set(cls.paths) == paths
    hosts = {c["HOST"]} if "HOST" in c else set(re.findall(r"// @match +https://([^/*]+)/", js))
    assert set(cls.hosts) == hosts

