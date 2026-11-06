"""framework/tools/health.py --until with the PR count reads the merges up to that time, also more than 10 commit pages back (#3072)."""
import datetime
import urllib.parse

import dashboard
import health
import pytest

NOW = datetime.datetime(2026, 10, 28, 12, 0, tzinfo=datetime.timezone.utc)
STEP = datetime.timedelta(seconds=190)
COMMITS = [{"commit": {"message": f"Change {i} (#{4000 - i})\n\nbody",
                       "committer": {"date": f"{NOW - i * STEP:%Y-%m-%dT%H:%M:%SZ}"}}} for i in range(4000)]


def api(path):
    """The commits API: newest first, 100 per page, with since= and until=."""
    q = dict(urllib.parse.parse_qsl(path.split("?", 1)[1]))
    since, until = (q.get(k) and dashboard.ts(q[k]) for k in ("since", "until"))
    cs = [c for c in COMMITS if (t := dashboard.ts(c["commit"]["committer"]["date"])) and
          (since is None or t >= since) and (until is None or t <= until)]
    page = int(q["page"])
    return cs[(page - 1) * 100:page * 100]


def test_merge_times_reach_three_days_back(monkeypatch):
    monkeypatch.setattr(dashboard, "api", api)
    until = NOW - datetime.timedelta(days=3)
    times = health.merge_times(100, until)
    assert len(times) == 101 and times[0] <= until


def test_pr_hours_names_the_count_of_too_few_merges(capsys):
    times = [NOW - i * STEP for i in range(30)]
    assert health.pr_hours(times, NOW, 50) == (29 * 190 / 3600, 0.0)     # a young repository: the oldest merge ends it
    assert "only 30 merge times" in capsys.readouterr().err
    with pytest.raises(SystemExit, match="no merged PR"):
        health.pr_hours([], NOW, 50)
