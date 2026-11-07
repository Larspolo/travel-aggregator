"""The roadmap review ends an idle stretch once (#491). With no ready ticket no PR merges, so the merged count of the
roadmap review (at least ROADMAP_IDLE_MIN, #5818) never came, and the queue stood idle 6.5 h on 2026-11-07; a review
then made 3 epics. The stretch gets one review, ROADMAP_IDLE minutes after the last lock or merge, and its lock holds
until a PR merges (the brake of #5818). health.py counts the wait for that clock as idle with work."""
import datetime

import claim
import health
import usage

LAST = "2026-11-07T02:40:00Z"


def slot(monkeypatch, merged=0, ready=0, live=0, idle=claim.ROADMAP_IDLE, newest=None, starved=True):
    monkeypatch.setattr(claim, "HELD", set())
    monkeypatch.setattr(claim, "on_github", lambda remote="origin": True)
    monkeypatch.setattr(claim, "api", lambda path, *a, **k: {"body": ""})
    monkeypatch.setattr(claim, "agent_state", lambda body: {"last_roadmap": LAST})
    monkeypatch.setattr(claim, "last_lock", lambda kind, remote="origin": None)
    monkeypatch.setattr(claim, "newest_lock", lambda kind, remote="origin": newest)
    monkeypatch.setattr(claim, "merged_since", lambda last, gap, remote="origin": merged)
    monkeypatch.setattr(claim, "idle_minutes", lambda last, remote="origin": idle)
    monkeypatch.setattr(claim, "live_runs", lambda remote="origin": live)
    monkeypatch.setattr(claim, "ready_tickets", lambda remote="origin": ready)
    return claim.review_slot("roadmap", starved=lambda: starved)[0]


def test_an_idle_stretch_gets_one_roadmap_review(monkeypatch):
    assert slot(monkeypatch, newest=(30, "refs/heads/claim/roadmap-30pr-x-1")) == f"0pr-{LAST.replace('-', '').replace(':', '')}-1"
    assert slot(monkeypatch) is not None                              # no lock yet: the state time starts the stretch


def test_no_second_review_in_the_same_stretch(monkeypatch):
    stretch_lock = (0, "refs/heads/claim/roadmap-0pr-x-1")
    assert slot(monkeypatch, newest=stretch_lock) is None              # no merge after the lock of the stretch
    assert slot(monkeypatch, newest=stretch_lock, idle=10 * claim.ROADMAP_IDLE) is None
    assert slot(monkeypatch, merged=1, newest=stretch_lock) == f"1pr-{LAST.replace('-', '').replace(':', '')}-1"


def test_the_stretch_needs_an_empty_queue_with_no_run(monkeypatch):
    assert slot(monkeypatch, ready=1) is None
    assert slot(monkeypatch, ready=None) is None                       # a read error is not an empty queue
    assert slot(monkeypatch, live=1) is None
    assert slot(monkeypatch, live=None) is None
    assert slot(monkeypatch, starved=False) is None                    # the refill has a source


def test_the_stretch_waits_for_the_clock_and_says_so(monkeypatch):
    assert slot(monkeypatch, idle=claim.ROADMAP_IDLE - 1) is None
    assert claim.HELD == {"roadmap"}
    assert usage.stretch_note() == f"; {usage.STRETCH}"
    slot(monkeypatch)
    assert claim.HELD == set() and usage.stretch_note() == ""


def test_health_counts_the_wait_of_the_stretch_as_idle_with_work():
    until = datetime.datetime(2026, 11, 7, 12, 0, tzinfo=datetime.timezone.utc)

    def cycle(at, line):
        return {"at": f"2026-11-07T{at}:00Z", "target": 8, "claims": 0, "ready": 0, "refill": 0, "started": {},
                "line": f"refill 0 (ready 0, target 8: no refill source{line}) · paused False"}
    cycles = [cycle("09:00", f"; {usage.STRETCH}"), cycle("10:00", ""), cycle("11:00", f"; {usage.STRETCH}")]
    assert health.idle_queue(cycles, until) == (3.0, 3.0, 1.0)
