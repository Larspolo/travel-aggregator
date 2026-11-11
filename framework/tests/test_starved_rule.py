"""One "starved" rule for the early roadmap review (#2239): the pacer (`usage.fire`) and the lock
(`claim.refill_starved`) agree, so the pacer starts no deep run for a review that `claim.py 0 --roadmap` does not give."""
import inspect

import claim
import usage
from test_epic_hold import NOW, epic


def test_an_open_epic_check_is_a_source_so_the_refill_is_not_starved():
    assert usage.starved(0, 4, [epic(9)], now=NOW) is False


def test_a_batch_of_two_close_checks_is_a_source_too():   # #2223 and #2214 on 2026-11-11
    deep = [epic(10), epic(11)]
    for e in deep:
        e["labels"].append({"name": "lane:deep"})
    assert usage.starved(0, 4, deep, now=NOW) is False


def test_no_epic_check_and_no_free_source_is_starved():
    assert usage.starved(0, 4, [], now=NOW) is True


def test_a_free_source_or_enough_ready_tickets_is_not_starved():
    assert usage.starved(0, 4, [], free=lambda: ["feature x"], now=NOW) is False
    assert usage.starved(4, 4, [], now=NOW) is False
    assert usage.starved(0, None, [], now=NOW) is False


def test_the_pacer_and_the_lock_use_the_same_rule():
    assert "usage.starved(" in inspect.getsource(claim.refill_starved)
    assert "starved(ready, target, open_all" in inspect.getsource(usage.fire)
