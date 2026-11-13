"""The planned platforms of a Trainline leg: each leg end gives its platform text, or None when the payload has no
valid text (#2770, epic #2769). The trip page shows them as "planned platform 1 → 2" and as the transfer platforms."""

import copy
import json
import re
from pathlib import Path

import pytest

from app.parsers.trainline import TrainlineParser
from tests.test_capture_upload import _post, client, trip_id  # noqa: F401  (fixtures)

FIX = Path(__file__).parent / "fixtures" / "thetrainline.com"
LONDON = FIX / "search-london-edinburgh.json"
AMSTERDAM = FIX / "search-amsterdam-berlin.json"
LNER_1003 = "47fa64f6-5941-452c-a596-9db253c9a6c1"
LNER_1033 = "3428ddcd-1a7f-4984-86c5-5dbea84afbc6"


def _legs(raw):
    """The legs of the London search of a payload: {leg id: leg dict}."""
    return raw["response"]["data"]["journeySearch"]["legs"] if "response" in raw else raw["data"]["journeySearch"]["legs"]


def _by_depart(offers, hhmm):
    return [o for o in offers if o.legs[0].depart_at.strftime("%H:%M") == hhmm]


def test_london_legs_give_their_planned_platforms():
    offers = TrainlineParser().parse(json.loads(LONDON.read_text(encoding="utf-8"))).offers
    lner = _by_depart(offers, "10:03")
    assert lner and all(o.legs[0].from_platform == "1" and o.legs[0].to_platform == "2" for o in lner)
    conn = _by_depart(offers, "10:33")
    assert conn and all(
        (o.legs[0].from_platform, o.legs[0].to_platform) == ("0F", "5")
        and (o.legs[1].from_platform, o.legs[1].to_platform) == ("11", "2")
        for o in conn
    )


@pytest.mark.parametrize("platforms", [
    None,                           # no `platforms` key
    {"origin": {"platform": None}, "destination": {"platform": None}},
    {"origin": {"platform": ""}, "destination": {"platform": ""}},
    {"origin": {"platform": "12345678901"}, "destination": {"platform": "12345678901"}},  # 11 characters
    {"origin": None, "destination": "2"},
])
def test_a_platform_that_is_no_valid_text_gives_none(platforms):
    raw = json.loads(LONDON.read_text(encoding="utf-8"))
    leg = _legs(raw)[LNER_1003]
    if platforms is None:
        leg.pop("platforms", None)
    else:
        leg["platforms"] = copy.deepcopy(platforms)
    offers = TrainlineParser().parse(raw).offers
    first = _by_depart(offers, "10:03")[0].legs[0]
    assert first.from_platform is None and first.to_platform is None
    # the other legs keep their platforms
    assert _by_depart(offers, "10:33")[0].legs[1].to_platform == "2"


def test_ten_characters_is_still_a_platform():
    raw = json.loads(LONDON.read_text(encoding="utf-8"))
    _legs(raw)[LNER_1003]["platforms"]["origin"]["platform"] = "1234567890"
    first = _by_depart(TrainlineParser().parse(raw).offers, "10:03")[0].legs[0]
    assert first.from_platform == "1234567890"


def test_amsterdam_berlin_gives_no_platform_on_any_leg():
    offers = TrainlineParser().parse(json.loads(AMSTERDAM.read_text(encoding="utf-8"))).offers
    assert offers
    for o in offers:
        for leg in o.legs:
            assert leg.from_platform is None and leg.to_platform is None


def test_parser_version_is_1_5_0():
    assert TrainlineParser.version == "1.5.0"


def _rows(page):
    parts = re.split(r'(?=<tr id="it-)', page)
    return {re.match(r'<tr id="(it-\d+)"', x).group(1): x for x in parts[1:]}


def _post_london(client, trip_id, raw=None):  # noqa: F811
    content = LONDON.read_bytes() if raw is None else json.dumps(raw).encode()
    assert _post(client, trip_id, source="thetrainline.com", content=content).status_code == 303


def test_trip_page_shows_the_planned_platforms(client, trip_id):  # noqa: F811
    _post_london(client, trip_id)
    rows = _rows(client.get(f"/trips/{trip_id}").text)
    assert any("planned platform 1 → 2" in x for x in rows.values())
    assert any("platform 5 → 11" in x for x in rows.values())
