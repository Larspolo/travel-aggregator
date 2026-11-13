"""cycle_start.py accepts an owner check that closed as completed: `close.yml` removes its `needs-human`."""
import cycle_start as start

BODY = "## Goal\nx\n\n## Owner checks\n- After #11, #12: on the preview, turn on the step.\n\n## Criteria\n- [ ] y\n"


def epic():
    return {"number": 5, "title": "Epic", "body": BODY, "labels": [{"name": "epic"}]}


def sub(title="Fix it", labels=(), reason="completed"):
    return {"number": 6, "title": title, "state": "closed", "state_reason": reason,
            "labels": [{"name": n} for n in labels]}


def missing(*subs):
    return start.owner_check_missing({5: epic()}, lambda n: list(subs))


def test_a_completed_check_by_title_gives_none():
    assert missing(sub("Owner check: the mark on a real search")) == []
    assert missing(sub("Check the warning with a real bahn.de search")) == []


def test_a_completed_check_by_label_or_audience_gives_none():
    assert missing(sub(labels=["check"])) == []
    assert missing(sub(labels=[next(iter(start.CONFIG["audience"]))])) == []


def test_a_check_closed_as_not_planned_still_gives_the_line():
    assert len(missing(sub("Owner check: x", ["check"], reason="not_planned"))) == 1


def test_an_other_completed_sub_issue_still_gives_the_line():
    assert len(missing(sub("Store the part price", ["feature"]))) == 1
