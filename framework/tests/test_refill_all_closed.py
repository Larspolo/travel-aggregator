"""framework/tools/claim.py --refill: the lock of an epic with all sub-issues closed expires with the 10-minute slot (#3057)."""
import claim

T = 1793188860                                                      # 2026-10-28 12:01 UTC


def state(monkeypatch, summary, now=T):
    monkeypatch.setattr(claim, "on_github", lambda remote="origin": True)
    monkeypatch.setattr(claim, "api", lambda path: {"number": 7, "sub_issues_summary": summary})
    return claim.refill_state(7, now=now)


def test_all_closed_locks_the_slot(monkeypatch):
    done = {"completed": 100, "total": 100}
    assert state(monkeypatch, done) == state(monkeypatch, done, T + 240)        # 12:05: the same lock
    assert state(monkeypatch, done, T + 840) != state(monkeypatch, done)        # 12:15: a new lock
    assert state(monkeypatch, done).startswith("100-")                          # the count stays in the key


def test_an_open_sub_issue_keeps_the_count(monkeypatch):
    part = {"completed": 2, "total": 3}
    assert state(monkeypatch, part) == state(monkeypatch, part, T + 840) == "2"
