"""An idle stretch with 1 to 9 merged PRs after the last roadmap lock gets its review at once (#1889). The clock of
ROADMAP_IDLE minutes kept the queue idle: 1.0 h longest, 2.9 h sum on 2026-11-10, while the review was the only work
that could fill the queue. A merge after the last lock is a new input, so the review need not wait. With no merge after the
last lock the input is the same: a stretch lock stops a second review (the brake of #5818), and after another lock
the review waits for the clock (a review that a run did not finish opens again)."""
import claim

LAST = "2026-11-10T03:32:00Z"
KEY = LAST.replace("-", "").replace(":", "")


def slot(monkeypatch, merged=0, idle=0, newest=None, ready=0, live=0):
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
    return claim.review_slot("roadmap", starved=lambda: True)[0]


def test_a_merge_after_the_last_lock_starts_the_review_at_once(monkeypatch):
    stretch_lock = (0, "refs/heads/claim/roadmap-0pr-x-1")
    for merged in range(1, claim.ROADMAP_IDLE_MIN):
        assert slot(monkeypatch, merged=merged, newest=stretch_lock) == f"{merged}pr-{KEY}-1"
        assert claim.HELD == set()                      # no "waits for the idle stretch" line in the pacer
    assert slot(monkeypatch, merged=3, newest=(30, "refs/heads/claim/roadmap-30pr-x-1")) == f"3pr-{KEY}-1"


def test_no_merge_after_the_stretch_lock_gives_no_review(monkeypatch):
    stretch_lock = (2, "refs/heads/claim/roadmap-2pr-x-1")
    assert slot(monkeypatch, newest=stretch_lock) is None
    assert slot(monkeypatch, newest=stretch_lock, idle=10 * claim.ROADMAP_IDLE) is None


def test_no_merge_after_another_lock_still_waits_for_the_clock(monkeypatch):
    regular = (30, "refs/heads/claim/roadmap-30pr-x-1")
    assert slot(monkeypatch, newest=regular, idle=claim.ROADMAP_IDLE - 1) is None
    assert claim.HELD == {"roadmap"}                    # health.idle_queue counts this wait as idle with work
    assert slot(monkeypatch, newest=regular, idle=claim.ROADMAP_IDLE) == f"0pr-{KEY}-1"


def test_a_merge_does_not_start_the_review_outside_a_stretch(monkeypatch):
    assert slot(monkeypatch, merged=3, ready=1) is None
    assert slot(monkeypatch, merged=3, live=1) is None
