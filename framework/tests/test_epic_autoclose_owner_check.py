"""An open owner check (`needs-human`) does not keep an epic open when its close line is met (#922: #779, #689 and
#718 stayed open with only an owner check sub-issue)."""
import epic_autoclose
import usage
from test_epic_autoclose import CHECK, NOW, agent, epic

WAITS = epic() | {"sub_issues_summary": {"total": 4, "completed": 3}}   # one open sub-issue


def sub(number, *labels, state="open"):
    return {"number": number, "state": state, "labels": [{"name": n} for n in labels]}


def select(subs, closed=None):
    return epic_autoclose.select([WAITS], lambda e: [agent(CHECK)], ({805: 830} if closed is None else closed).get, now=NOW,
                                 sub_issues_of=lambda e: subs)


def test_an_open_owner_check_does_not_keep_the_epic_open():
    out = select([sub(805, state="closed"), sub(807, "needs-human", "for-jeroen")])
    assert [(e, n, pr) for e, n, pr, _ in out] == [(9, (805,), (830,))]


def test_an_open_sub_issue_without_needs_human_keeps_the_epic_open():
    assert select([sub(805, state="closed"), sub(806, "feature"), sub(807, "needs-human")]) == []


def test_the_ticket_of_the_line_must_still_merge():
    assert select([sub(807, "needs-human")], closed={}) == []


def test_a_held_epic_with_an_owner_check_stays_open():
    held = WAITS | {"labels": [{"name": "epic"}, {"name": "muted"}]}
    assert epic_autoclose.select([held], lambda e: [agent(CHECK)], {805: 830}.get, now=NOW,
                                 sub_issues_of=lambda e: [sub(807, "needs-human")]) == []


def test_the_pacer_still_starts_no_check_for_the_epic():
    assert usage.epic_checks([WAITS], NOW) == []


def test_an_owner_check_with_part_of_does_not_keep_the_epic_open():
    check = {"number": 743, "labels": [{"name": "needs-human"}], "body": "Part of #9"}
    issues = [WAITS, check]
    out = epic_autoclose.select(issues, lambda e: [agent(CHECK)], {805: 830}.get, now=NOW,
                                sub_issues_of=lambda e: [sub(743, "needs-human")])
    assert [e for e, *_ in out] == [9]
    other = {"number": 744, "labels": [{"name": "feature"}], "body": "Part of #9"}
    assert epic_autoclose.select(issues + [other], lambda e: [agent(CHECK)], {805: 830}.get, now=NOW,
                                 sub_issues_of=lambda e: [sub(743, "needs-human")]) == []
