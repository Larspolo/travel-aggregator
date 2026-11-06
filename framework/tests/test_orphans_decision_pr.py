"""An orphan decision that an open PR closes names the PR: the owner answered, and the PR waits for its merge (#4754)."""
import dashboard


def test_a_decision_with_an_open_pr_names_the_pr():
    issues = [{"number": 6, "title": "Decide: the colour", "labels": [{"name": "P3"}], "body": ""},
              {"number": 9, "title": "Record the decision (#6)", "labels": [], "body": "Close #6.", "pull_request": {}}]
    got = dict(dashboard.orphans(issues))
    assert "PR #9" in got[6] and "automerge" in got[6]
