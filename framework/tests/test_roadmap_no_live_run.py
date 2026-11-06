"""The roadmap review of a starved refill is due at once when no run holds a live claim: then no run can merge a PR or
make a ticket, so the wait of ROADMAP_IDLE minutes waits for nothing. On 2026-11-01 and 2026-11-02 the queue stood
idle 13 times for about 1 h each (pacer log: "ready 0", "claims 0", then "roadmap review due")."""
import claim

LAST = "2026-11-02T17:50:00Z"


def slot(monkeypatch, merged=claim.ROADMAP_IDLE_MIN, idle=5, live=0, starved=True):
    monkeypatch.setattr(claim, "on_github", lambda remote="origin": True)
    monkeypatch.setattr(claim, "api", lambda path, *a, **k: {"body": ""})
    monkeypatch.setattr(claim, "agent_state", lambda body: {"last_roadmap": LAST})
    monkeypatch.setattr(claim, "last_lock", lambda kind, remote="origin": None)
    monkeypatch.setattr(claim, "merged_since", lambda last, gap, remote="origin": merged)
    monkeypatch.setattr(claim, "idle_minutes", lambda last, remote="origin": idle)
    monkeypatch.setattr(claim, "live_runs", lambda remote="origin": live)
    return claim.review_slot("roadmap", starved=lambda: starved)[0]


def test_no_live_run_makes_the_roadmap_review_due_at_once(monkeypatch):
    assert slot(monkeypatch, live=0) is not None


def test_a_live_run_keeps_the_wait_for_its_merge(monkeypatch):
    assert slot(monkeypatch, live=1) is None
    assert slot(monkeypatch, live=None) is None                      # git cannot read the claims: wait as before
    assert slot(monkeypatch, live=1, idle=claim.ROADMAP_IDLE) is not None   # the clock still ends a lost run


def test_the_other_conditions_stay(monkeypatch):
    assert slot(monkeypatch, merged=0, live=0) is None               # no PR merged since the last roadmap review
    assert slot(monkeypatch, merged=claim.ROADMAP_IDLE_MIN - 1, live=0) is None   # too few PRs for a change (#5818)
    assert slot(monkeypatch, live=0, starved=False) is None          # the refill has a source
