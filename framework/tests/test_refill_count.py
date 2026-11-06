"""The pacer starts the refill runs from the tickets that the queue misses, not from a fixed count and gap (owner, 2026-11-06)."""
import usage

NOW = 1_800_000_000


def test_one_refill_run_for_each_four_missing_tickets():
    assert usage.refill_count(ready=0, target=4, live=0, epics=5, per=4, most=8) == 1
    assert usage.refill_count(ready=1, target=16, live=0, epics=5, per=4, most=8) == 4
    assert usage.refill_count(ready=2, target=10, live=0, epics=5, per=4, most=8) == 2


def test_one_refill_run_when_the_queue_is_full_but_a_check_waits():
    assert usage.refill_count(ready=12, target=4, live=0, epics=5) == 1      # an epic check or a review: one run


def test_the_live_refill_runs_count():
    assert usage.refill_count(ready=1, target=16, live=3, epics=5, per=4, most=8) == 1
    assert usage.refill_count(ready=3, target=4, live=1, epics=5) == 0      # the live run makes the missing ticket


def test_no_more_refill_runs_than_the_limit_and_the_sources():
    assert usage.refill_count(ready=0, target=16, live=0, epics=5, per=4, most=3) == 3
    assert usage.refill_count(ready=0, target=16, live=0, epics=1, per=4, most=8) == 2   # the whole refill and one epic
    assert usage.refill_count(ready=0, target=16, live=0, epics=5, new=False, per=4, most=8) == 1   # no new ticket


def test_a_refill_lock_is_live_for_its_minutes_and_counts_each_run_once():
    lines = [f"refill-0-2026110614-3 {NOW - 60} Claim refill 0-2026110614-3 by ccr-abc (1)",
             f"refill-140-2 {NOW - 120} Claim refill 140-2 by ccr-abc (2)",           # the same run, a second epic
             f"refill-134-1 {NOW - 300} Claim refill 134-1 by pacer-r9f (3)",
             f"refill-141-0 {NOW - 3600} Claim refill 141-0 by ccr-old (4)",          # older than the minutes
             f"141 {NOW - 30} Claim #141 by ccr-new lane deep"]                       # a ticket claim, no refill
    assert usage.refill_live(lines, NOW, minutes=20) == 2
    assert usage.refill_live(lines, NOW, minutes=90) == 3
    assert usage.refill_live(None, NOW) == 0
