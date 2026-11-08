"""An open `needs-human` ticket on a roadmap line holds the feature also with no `Kind:` line in its body (#1059): the
owner issue #1036 of `rank:return-fare` got its question in a comment, and the pacer started deep refill runs that
found no source. Only an input ticket (`Kind: outside` or `Kind: setting`) does not hold: the epic starts with it."""
import dashboard
import usage

OWNER_ISSUE = "### Goal\n\nA flight is usually return.\n\n### Priority\n\nP2"


def issue(labels, body):
    return {"state": "open", "labels": [{"name": n} for n in labels], "body": body}


def stub(monkeypatch, issues):
    monkeypatch.setattr(dashboard, "api", lambda path: issues[int(path.rsplit("/", 1)[1])])


def test_an_owner_issue_with_a_question_holds_the_feature(monkeypatch):
    stub(monkeypatch, {1036: issue(["needs-human", "feature", "for-jeroen"], OWNER_ISSUE)})
    assert usage.held({1036})


def test_a_question_ticket_holds_the_feature(monkeypatch):
    stub(monkeypatch, {7: issue(["needs-human"], "## Goal\nX.\n\n## For the owner\nKind: question\n1. Reply.")})
    assert usage.held({7})


def test_a_setting_input_does_not_hold_it(monkeypatch):
    stub(monkeypatch, {8: issue(["needs-human"], "## Goal\nX.\n\n## For the owner\nKind: setting\n1. Set it.")})
    assert not usage.held({8})


def test_the_same_owner_issue_without_needs_human_does_not_hold_it(monkeypatch):
    stub(monkeypatch, {1036: issue(["feature"], OWNER_ISSUE)})
    assert not usage.held({1036})
