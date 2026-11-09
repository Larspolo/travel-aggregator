"""cycle_start.py shows an epic whose owner check ticket is missing (#1342)."""
import cycle_start as start

BODY = "## Goal\nx\n\n## Owner checks\n- After #11, #12: on the preview, turn on the step.\n\n## Criteria\n- [ ] y\n"


def epic(body=BODY):
    return {"number": 5, "title": "Epic", "body": body, "labels": [{"name": "epic"}]}


def test_all_closed_no_owner_ticket_gives_one_line():
    lines = start.owner_check_missing({5: epic()}, lambda n: [{"labels": []}])
    assert len(lines) == 1 and lines[0].startswith("#5 ") and "After #11, #12" in lines[0]


def test_open_ticket_gives_none():
    assert start.owner_check_missing({5: epic(), 12: {"number": 12, "labels": []}}, lambda n: []) == []


def test_needs_human_sub_issue_gives_none():
    subs = [{"labels": [{"name": "needs-human"}], "state": "open"}]
    assert start.owner_check_missing({5: epic()}, lambda n: subs) == []


def test_no_section_or_not_epic_gives_none():
    assert start.owner_check_missing({5: epic("## Goal\n- After #11: x\n")}, lambda n: []) == []
    assert start.owner_check_missing({5: dict(epic(), labels=[])}, lambda n: []) == []
