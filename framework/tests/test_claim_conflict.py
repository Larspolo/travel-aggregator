"""framework/tools/claim.py: a ticket whose PR has the label `conflict` is stale after 10 minutes, not 30 (#1773)."""
import datetime

import claim

NOW = datetime.datetime(2026, 10, 27, 17, 0, tzinfo=datetime.timezone.utc).timestamp()


def pr(n, body, labels=("conflict",), pushed_ago=12, state="open"):
    return {"number": n, "body": body, "state": state, "labels": [{"name": x} for x in labels],
            "head": {"sha": "a" * 40}, "pushed": NOW - pushed_ago * 60}


def pushed(p):
    return p["pushed"]


def test_conflicted_pr_with_an_old_beat_is_free_after_10_minutes():
    pulls = [pr(1760, "Closes #1750")]
    assert claim.conflict_pr(pulls, 1750, NOW, pushed) == 1760
    limit = claim.CONFLICT
    beat = NOW - 11 * 60
    assert claim.stale("Beat #1750 by run-0", beat, NOW, limit)                   # free after 10 minutes
    assert not claim.stale("Beat #1750 by run-0", beat, NOW)                       # 30 minutes without a conflict


def test_recent_beat_or_commit_keeps_the_pr():
    assert not claim.stale("Beat #1750 by run-0", NOW - 4 * 60, NOW, claim.CONFLICT)   # the run is alive
    assert claim.conflict_pr([pr(1760, "Closes #1750", pushed_ago=3)], 1750, NOW, pushed) is None  # a new commit
    assert claim.conflict_pr([pr(1760, "Closes #1750", labels=())], 1750, NOW, pushed) is None     # no conflict
    assert claim.conflict_pr([pr(1760, "Closes #1751")], 1750, NOW, pushed) is None                # another ticket
    assert claim.conflict_pr([pr(1760, "Closes #1750", state="closed")], 1750, NOW, pushed) is None


def test_local_remote_keeps_30_minutes(monkeypatch):
    monkeypatch.setattr(claim, "on_github", lambda remote="origin": False)
    assert claim.stale_limit(1750) == claim.STALE
