"""The Trainline parser gives a high notice to each leg that runs as a replacement service (#2790)."""

import copy
import json
from pathlib import Path

from app.parsers.trainline import TrainlineParser

FIX = Path(__file__).parent / "fixtures" / "thetrainline.com" / "search-london-edinburgh.json"
TEXT = "Replacement service in place of the scheduled train"


def load():
    return json.loads(FIX.read_text(encoding="utf-8"))


def test_fixture_as_it_is_gives_no_notices():
    result = TrainlineParser().parse(load())
    assert result.offers
    assert all(o.notices == [] for o in result.offers)


def test_replacement_flag_on_the_leg_of_the_1003_train_gives_one_high_notice():
    raw = load()
    search = raw["response"]["data"]["journeySearch"]
    journey = next(j for j in search["journeys"].values() if j["legs"] and
                   search["legs"][j["legs"][0]]["departAt"][11:16] == "10:03")
    search["legs"][journey["legs"][0]]["replacementServiceInfo"] = {"isReplacementService": True}
    result = TrainlineParser().parse(raw)
    hit = [o for o in result.offers if o.external_id == journey["id"]]
    assert hit
    for offer in hit:
        assert len(offer.notices) == 1
        assert offer.notices[0].text == TEXT
        assert offer.notices[0].level == "high"
        assert offer.notices[0].leg == 0


def test_true_on_second_leg_gives_leg_1():
    raw = load()
    search = raw["response"]["data"]["journeySearch"]
    journey = next(j for j in search["journeys"].values() if len(j["legs"]) == 2)
    for i, leg_id in enumerate(journey["legs"]):
        search["legs"][leg_id]["replacementServiceInfo"] = {"isReplacementService": i == 1}
    result = TrainlineParser().parse(raw)
    hit = [o for o in result.offers if o.external_id == journey["id"]]
    assert hit
    for offer in hit:
        assert [(n.leg, n.level) for n in offer.notices] == [(1, "high")]


def test_false_on_every_leg_gives_an_empty_list():
    raw = load()
    for leg in raw["response"]["data"]["journeySearch"]["legs"].values():
        leg["replacementServiceInfo"] = {"isReplacementService": False}
    result = TrainlineParser().parse(raw)
    assert result.offers
    assert all(o.notices == [] for o in result.offers)


def test_a_leg_without_the_key_gives_no_error():
    raw = copy.deepcopy(load())
    legs = raw["response"]["data"]["journeySearch"]["legs"]
    legs[next(iter(legs))]["replacementServiceInfo"] = {"isReplacementService": True}
    result = TrainlineParser().parse(raw)
    assert not result.errors
    assert result.offers
