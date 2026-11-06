"""A ready ticket keeps the early roadmap review of a starved refill waiting, like a live run (#851). The pacer saw no
live run and a ready ticket, said "roadmap review due" and started a ticket run and a deep run in the same cycle; the
claim of the ticket run made the review not due a minute later, and the deep run found no work (5 of 47 deep runs on
2026-11-03)."""
import claim

LAST = "2026-11-03T16:00:00Z"


def slot(monkeypatch, ready=1, live=0, idle=5):
    monkeypatch.setattr(claim, "on_github", lambda remote="origin": True)
    monkeypatch.setattr(claim, "api", lambda path, *a, **k: {"body": ""})
    monkeypatch.setattr(claim, "agent_state", lambda body: {"last_roadmap": LAST})
    monkeypatch.setattr(claim, "last_lock", lambda kind, remote="origin": None)
    monkeypatch.setattr(claim, "merged_since", lambda last, gap, remote="origin": claim.ROADMAP_IDLE_MIN)
    monkeypatch.setattr(claim, "idle_minutes", lambda last, remote="origin": idle)
    monkeypatch.setattr(claim, "live_runs", lambda remote="origin": live)
    monkeypatch.setattr(claim, "ready_tickets", lambda remote="origin": ready)
    return claim.review_slot("roadmap", starved=lambda: True)[0]


def test_a_ready_ticket_keeps_the_wait_for_its_run(monkeypatch):
    assert slot(monkeypatch, ready=1) is None


def test_no_ready_ticket_and_no_live_run_is_due_at_once(monkeypatch):
    assert slot(monkeypatch, ready=0) is not None
    assert slot(monkeypatch, ready=None) is not None                  # a read error: due, as before #851


def test_the_clock_still_ends_the_wait(monkeypatch):
    assert slot(monkeypatch, ready=1, idle=claim.ROADMAP_IDLE) is not None


def test_ready_tickets_counts_the_candidates_of_all_lanes(monkeypatch):
    import dashboard
    issues = [{"number": 7}, {"number": 8}]
    monkeypatch.setattr(claim, "api", lambda path: issues)
    monkeypatch.setattr(dashboard, "candidates", lambda got, reserved=None: got if reserved == () else [])
    assert claim.ready_tickets() == 2
    monkeypatch.setattr(claim, "api", lambda path: claim.fail("GitHub API failed"))
    assert claim.ready_tickets() is None
