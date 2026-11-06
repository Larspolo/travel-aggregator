"""framework/tools/claim.py does not claim a ticket whose PR of another run is active (#491), with fixed API data."""
import datetime

import claim
from test_claim import clones  # noqa: F401  (fixture)

NOW = datetime.datetime(2026, 10, 26, 5, 0, tzinfo=datetime.timezone.utc)


def pr(n, ref, body, minutes_ago, state="open"):
    t = (NOW - datetime.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"number": n, "head": {"ref": ref}, "body": body, "state": state, "updated_at": t}


def test_active_pr():
    now = NOW.timestamp()
    assert claim.active_pr([pr(471, "run-0", "...\nCloses #428", 14)], 428, "run-1", now) == 471
    assert claim.active_pr([pr(471, "run-0", "Closes #428", 31)], 428, "run-1", now) is None    # stalled
    assert claim.active_pr([pr(471, "run-1", "Closes #428", 1)], 428, "run-1", now) is None     # the own PR
    assert claim.active_pr([pr(471, "run-0", "Closes #4280", 1)], 428, "run-1", now) is None    # another ticket
    assert claim.active_pr([pr(471, "run-0", None, 1)], 428, "run-1", now) is None
    assert claim.active_pr([pr(471, "run-0", "Closes #428", 1, "closed")], 428, "run-1", now) is None


def test_claim_and_takeover_with_an_active_pr(clones, monkeypatch):  # noqa: F811
    a, _, _ = clones
    fresh = pr(471, "run-9", "Closes #12", 0)                         # clone a is the run of branch run-0
    fresh["updated_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    monkeypatch.setattr(claim, "on_github", lambda remote="origin": True)
    monkeypatch.setattr(claim, "api", lambda path: [fresh] if path.startswith("pulls") else [])
    monkeypatch.chdir(a)
    assert claim.main(["12"]) == 1 and claim.refs(12) == {}          # the run of PR #471 still works
    assert claim.main(["12", "--takeover"]) == 0                     # a takeover does not look at the PRs
    fresh.update(body="Closes #13", updated_at="2026-10-26T04:00:00Z")   # stalled: the claim is free
    assert claim.main(["13"]) == 0
