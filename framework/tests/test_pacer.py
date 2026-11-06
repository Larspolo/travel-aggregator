"""The pacer starts the runs that the quota target misses (#566): runs cannot start other runs."""
import usage


def test_start_the_missing_runs_up_to_the_cycle_limit():
    assert usage.runs_to_start(target=6, claims=4, ready=10, paused=False) == 2
    assert usage.runs_to_start(target=15, claims=1, ready=10, paused=False) == usage.MAX_FIRE


def test_start_no_more_runs_than_ready_tickets_and_the_refill_runs():
    assert usage.runs_to_start(target=15, claims=1, ready=2, paused=False, refill=1) == 3
    assert usage.runs_to_start(target=15, claims=1, ready=0, paused=False, refill=1) == 1     # a refill run (#609)


def test_start_nothing_when_full_paused_or_out_of_quota():
    assert usage.runs_to_start(target=5, claims=7, ready=10, paused=False) == 0
    assert usage.runs_to_start(target=15, claims=0, ready=10, paused=True) == 0
    assert usage.runs_to_start(target=0, claims=0, ready=10, paused=False) == 0      # a window is rejected
    assert usage.runs_to_start(target=None, claims=0, ready=10, paused=False) == 0   # no usage data
