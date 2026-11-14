""""Waiting for you" groups the needs-human tickets by their assignee (#2867; by a label before, #72)."""
import dashboard

AUDIENCE = {"system": "Lead", "project": "Second"}


def issue(n, *logins):
    return dict(number=n, title=f"Ticket {n}", labels=[{"name": "needs-human"}], body="",
                assignees=[{"login": x} for x in logins])


def test_groups_by_assignee():
    lines = dashboard.waiting([issue(1, "Second"), issue(2, "Lead"), issue(3), issue(4, "other-login")], {}, AUDIENCE)
    text = "\n".join(lines)
    assert text.index("**For Lead**") < text.index("#2 ") < text.index("**For Second**") < text.index("#1 ")
    assert text.index("**Other**") < text.index("#3 ") < text.index("#4 ")


def test_a_ticket_for_two_persons_is_in_both_groups():
    lines = dashboard.waiting([issue(5, "Lead", "Second")], {}, AUDIENCE)
    assert [x for x in lines if x.startswith("- #5 ")] == [lines[1], lines[3]] and "**Other**" not in "\n".join(lines)


def test_one_person_with_both_roles_gets_one_group():
    lines = dashboard.waiting([issue(6, "Lead")], {}, {"system": "Lead", "project": "Lead"})
    assert lines[0] == "**For Lead**:" and len(lines) == 2


def test_no_audience_gives_flat_list():
    assert dashboard.waiting([issue(1)], {}, {})[0].startswith("- #1 ")
    assert dashboard.waiting([], {}, AUDIENCE) == ["- nothing"]
