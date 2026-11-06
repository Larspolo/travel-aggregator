"""framework/tools/cycle_start.py turns the first picks of each run, so that parallel runs claim other tickets first (#3832)."""
import cycle_start as start
from test_cycle_start import ticket

RUNS = [f"claude/run-{c}" for c in "abcdefgh"]


def numbers(picks):
    return [i["number"] for i in picks]


def test_eight_runs_give_at_least_four_first_picks():
    group = [ticket(n, "", "P2") for n in range(10, 18)]
    firsts = {numbers(start.spread_top(group, run))[0] for run in RUNS}
    assert len(firsts) >= 4, firsts


def test_a_higher_priority_stays_first_and_the_other_groups_keep_their_order():
    picks = [ticket(1, "", "P1")] + [ticket(n, "", "P2") for n in range(10, 14)] + [ticket(20, "", "P3"),
                                                                                    ticket(21, "", "P3")]
    for run in RUNS:
        got = numbers(start.spread_top(picks, run))
        assert got[0] == 1 and got[-2:] == [20, 21] and sorted(got[1:5]) == [10, 11, 12, 13]
    two = [ticket(2, "", "P1"), ticket(3, "", "P1")] + picks[1:]
    for run in RUNS:
        assert sorted(numbers(start.spread_top(two, run))[:2]) == [2, 3]    # the P1 group spreads, P2 stays below


def test_the_lane_tickets_of_a_main_run_stay_after_the_others():
    picks = [ticket(5, "", "P2"), ticket(6, "", "P2"), ticket(7, "", "P1", "lane:haiku")]
    for run in RUNS:
        assert numbers(start.spread_top(picks, run))[2] == 7


def test_the_same_run_gets_the_same_order_twice():
    group = [ticket(n, "", "P2") for n in range(10, 18)]
    for run in RUNS:
        assert numbers(start.spread_top(group, run)) == numbers(start.spread_top(group, run))


def test_only_the_first_eight_turn_and_no_item_is_lost():
    items = list(range(12))
    for run in RUNS:
        got = start.spread(items, run)
        assert sorted(got) == items and got[8:] == [8, 9, 10, 11]
    assert start.spread([], "x") == [] and start.spread([4], "x") == [4]


def test_two_runs_try_other_stuck_prs_first():
    lines = [f"PR #{n} (`claude/x-{n}`, #{n}): red CI: quick; no live claim: take it over" for n in range(5)]
    firsts = {start.spread(lines, run)[0] for run in RUNS}
    assert len(firsts) >= 3
