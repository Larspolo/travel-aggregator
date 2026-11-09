"""cycle_start.py accepts a closed owner-sample check as the owner check ticket of an epic (#1547)."""
import cycle_start as start

BODY = "## Goal\nx\n\n## Owner checks\n- After #11, #12: on the preview, turn on the step.\n\n## Criteria\n- [ ] y\n"


def epic():
    return {"number": 5, "title": "Epic", "body": BODY, "labels": [{"name": "epic"}]}


def sub(labels, state="closed"):
    return {"number": 6, "state": state, "labels": [{"name": n} for n in labels]}


def test_closed_owner_sample_check_gives_none():
    subs = [sub(["check", "owner-sample"])]
    assert start.owner_check_missing({5: epic()}, lambda n: subs) == []


def test_open_check_gives_none():
    subs = [sub(["check"], state="open")]
    assert start.owner_check_missing({5: epic()}, lambda n: subs) == []


def test_closed_check_without_owner_sample_still_gives_line():
    subs = [sub(["check"], state="closed")]
    lines = start.owner_check_missing({5: epic()}, lambda n: subs)
    assert len(lines) == 1 and "After #11, #12" in lines[0]
