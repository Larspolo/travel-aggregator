"""framework/tools/claim.py --refill: the slot lock of an epic with all sub-issues closed stays after its first new sub-issue
(#3454: the state changed from "4-<slot>" to "4", and a second run made the same sub-issues again)."""
from test_claim import clones, tool  # noqa: F401 (fixture)
from test_claim_refill import deep


def test_a_slot_lock_blocks_the_count_lock(clones):  # noqa: F811
    deep(clones)
    assert tool(clones[0], "2807", "--refill", "--state", "4-20261028221").returncode == 0   # all 4 closed: run A
    assert tool(clones[1], "2807", "--refill", "--state", "4").returncode == 1               # A made a 5th: run B
    assert tool(clones[1], "2807", "--refill", "--state", "5").returncode == 0               # a sub-issue closed


def test_no_slot_lock_gives_the_count_lock(clones):  # noqa: F811
    deep(clones)
    assert tool(clones[0], "908", "--refill", "--state", "4-20261028221").returncode == 0
    assert tool(clones[1], "908", "--refill", "--state", "3").returncode == 0                # another count
    assert tool(clones[1], "909", "--refill", "--state", "4").returncode == 0                # another epic
