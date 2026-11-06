"""framework/tools/health.py names the files of the PRs with a merge conflict (improve, run 150)."""
import datetime

import health

SINCE = datetime.datetime(2026, 10, 25, 12, 0, tzinfo=datetime.timezone.utc)


def test_conflicted_prs_and_their_files():
    url = "https://api.github.com/repos/Larspolo/travel-aggregator/issues/"
    comments = [{"issue_url": url + "7", "body": "CI is green, but the merge failed (not mergeable)."},
                {"issue_url": url + "9", "body": " CI is green, but the merge failed (not mergeable)."},
                {"issue_url": url + "7", "body": "CI is green, but the merge failed again."},
                {"issue_url": url + "8", "body": "Run of `claude/c`: PR #8 had a merge conflict."}]
    assert health.conflicted(comments) == [7, 9]
    files_of = {7: ["game/replay.py", "a.py", "a.py"], 9: ["game/replay.py"]}
    assert health.conflict_files(files_of) == [("game/replay.py", 2), ("a.py", 1)]
    text = health.report(SINCE, [], [], [], [], [], [], files_of)
    assert "Files of the 2 conflicted PRs (PRs): game/replay.py 2; a.py 1" in text
    assert "conflicted PRs" not in health.report(SINCE, [], [], [], [], [], [])
