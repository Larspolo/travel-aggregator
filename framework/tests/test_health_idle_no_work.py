"""The idle queue of the health report names its hours with no work (#854): an idle stretch of 19.7 h on 2026-11-03 had
`ready` 0 and `refill` 0 in each cycle (each ticket waited for the owner), and the process review searched the pacer
log to find that it was no fault of the pacer."""
import datetime

import health

UNTIL = datetime.datetime(2026, 11, 4, 14, 0, tzinfo=datetime.timezone.utc)


def cycle(at, ready=0, refill=0, claims=0, started=0, target=16):
    return {"at": f"2026-11-04T{at}:00Z", "target": target, "claims": claims, "ready": ready, "refill": refill,
            "started": {"deep": started}, "line": "paused False"}


def test_the_hours_with_no_ready_ticket_and_no_refill_source():
    cycles = [cycle("10:00"), cycle("11:00"), cycle("12:00", ready=1), cycle("13:00", started=1)]
    assert health.idle_queue(cycles, UNTIL) == (3.0, 3.0, 2.0)


def test_a_stretch_to_the_end_and_the_busy_cycles():
    cycles = [cycle("11:00", claims=1), cycle("12:00", refill=1), cycle("13:00")]
    assert health.idle_queue(cycles, UNTIL) == (2.0, 2.0, 1.0)
    assert health.idle_queue([], UNTIL) == (0.0, 0, 0)


def test_the_line_names_the_hours_with_no_work():
    out = health.report(UNTIL, [], [], [], [], [], [], idle=(3.0, 3.0, 2.0))
    assert "Idle queue (target > 0, no claim, no start): longest 3.0 h, sum 3.0 h (no work: 2.0 h, #854)" in out
